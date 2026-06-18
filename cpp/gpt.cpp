// ============================================================================
// The most atomic way to train and run inference for a GPT in pure,
// dependency-free C++. This file is the complete algorithm.
// Everything else is just efficiency.
//
// C++23 / std-only. Style: AAA, trailing returns, std::ranges,
// Number concept, using Type = ... aliases.
// ============================================================================
#include <algorithm>
#include <cmath>
#include <concepts>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <memory>
#include <numeric>
#include <random>
#include <ranges>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

// ---------------------------------------------------------------------------
// Concept: anything that behaves like a real number scalar.
// ---------------------------------------------------------------------------
template<typename T>
concept Number = std::floating_point<T> || std::integral<T>;

// ---------------------------------------------------------------------------
// Autograd: ValueNode<N> is a typed scalar node in the computation graph.
// ---------------------------------------------------------------------------
template<Number N>
struct ValueNode {
 using Scalar = N;
 using NodePtr = std::shared_ptr<ValueNode<N>>;
 using Children = std::vector<NodePtr>;
 using Gradients = std::vector<N>;

 Scalar data;
 Scalar grad = N{0};
 Children children = {};
 Gradients local_grads = {}; // d(this)/d(child)

 explicit ValueNode(Scalar d) : data(d) {}
 ValueNode(Scalar d, Children ch, Gradients lg)
 : data(d), children(std::move(ch)), local_grads(std::move(lg)) {}
};

// ---------------------------------------------------------------------------
// Value<N>: user-facing wrapper; builds the graph via operator overloads.
// ---------------------------------------------------------------------------
template<Number N>
class Value {
public:
 using Scalar = N;
 using Node = ValueNode<N>;
 using NodePtr = std::shared_ptr<Node>;

 NodePtr node;

 Value(Scalar d = N{0}) : node(std::make_shared<Node>(d)) {}
 Value(NodePtr n) : node(std::move(n)) {}

 auto data() const -> Scalar { return node->data; }
 auto grad() const -> Scalar { return node->grad; }
 auto set_data(Scalar d) -> void { node->data = d; }
 auto zero_grad() -> void { node->grad = N{0}; }

 auto operator+(const Value& o) const -> Value {
 return Value(std::make_shared<Node>(
 node->data + o.node->data,
 typename Node::Children{node, o.node},
 typename Node::Gradients{N{1}, N{1}}));
 }
 auto operator*(const Value& o) const -> Value {
 return Value(std::make_shared<Node>(
 node->data * o.node->data,
 typename Node::Children{node, o.node},
 typename Node::Gradients{o.node->data, node->data}));
 }
 auto pow(Scalar p) const -> Value {
 auto out = std::pow(node->data, p);
 return Value(std::make_shared<Node>(
 out,
 typename Node::Children{node},
 typename Node::Gradients{p * std::pow(node->data, p - N{1})}));
 }
 auto log() const -> Value {
 return Value(std::make_shared<Node>(
 std::log(node->data),
 typename Node::Children{node},
 typename Node::Gradients{N{1} / node->data}));
 }
 auto exp() const -> Value {
 auto e = std::exp(node->data);
 return Value(std::make_shared<Node>(
 e,
 typename Node::Children{node},
 typename Node::Gradients{e}));
 }
 auto relu() const -> Value {
 auto out = std::max(N{0}, node->data);
 return Value(std::make_shared<Node>(
 out,
 typename Node::Children{node},
 typename Node::Gradients{node->data > N{0} ? N{1} : N{0}}));
 }
 auto operator-() const -> Value { return *this * Value(N{-1}); }
 auto operator-(const Value& o) const -> Value { return *this + (-o); }
 auto operator/(const Value& o) const -> Value { return *this * o.pow(N{-1}); }

 // Topological sort, then reverse-mode chain rule.
 auto backward() -> void {
 auto topo = std::vector<NodePtr>{};
 auto visited = std::unordered_set<Node*>{};

 auto build = std::function<void(const NodePtr&)>{};
 build = [&](const auto& v) {
 if (visited.insert(v.get()).second) {
 for (const auto& c : v->children) build(c);
 topo.push_back(v);
 }
 };
 build(node);

 node->grad = N{1};
 for (const auto& v : topo | std::views::reverse)
 for (auto i : std::views::iota(0u, v->children.size()))
 v->children[i]->grad += v->local_grads[i] * v->grad;
 }
};

// ---------------------------------------------------------------------------
// Aliases: the types we use everywhere, all in one place.
// ---------------------------------------------------------------------------
using Scalar = double;
using Val = Value<Scalar>;
using Vector = std::vector<Val>;
using Matrix = std::vector<Vector>;
using Weights = std::vector<Scalar>; // raw float buffers (Adam moments, etc.)
using Tokens = std::vector<int>;
using Chars = std::vector<char>;
using KVCache = std::vector<std::vector<Vector>>; // [layer][time] -> embedding
using Dict = std::unordered_map<std::string, Matrix>;

auto vsum(const Vector& xs) -> Val {
 return std::accumulate(xs.begin(), xs.end(), Val(Scalar{0}),
 [](auto acc, const auto& x) { return acc + x; });
}

// ---------------------------------------------------------------------------
// Model ops: linear, softmax, rmsnorm.
// ---------------------------------------------------------------------------
auto linear(const Vector& x, const Matrix& w) -> Vector {
 auto out = Vector{};
 out.reserve(w.size());
 for (const auto& row : w) {
 auto s = std::inner_product(row.begin(), row.end(), x.begin(), Val(Scalar{0}),
 [](auto a, auto b) { return a + b; },
 [](auto wi, auto xi) { return wi * xi; });
 out.push_back(s);
 }
 return out;
}

auto softmax(const Vector& logits) -> Vector {
 auto max_val = std::ranges::max(logits | std::views::transform(&Val::data));
 auto exps = Vector{};
 exps.reserve(logits.size());
 std::ranges::transform(logits, std::back_inserter(exps),
 [max_val](const auto& v) { return (v - Val(max_val)).exp(); });
 auto total = vsum(exps);
 auto out = Vector{};
 out.reserve(exps.size());
 std::ranges::transform(exps, std::back_inserter(out),
 [&total](const auto& e) { return e / total; });
 return out;
}

auto rmsnorm(const Vector& x) -> Vector {
 auto sq = Vector{};
 sq.reserve(x.size());
 std::ranges::transform(x, std::back_inserter(sq), [](const auto& xi) { return xi * xi; });
 auto ms = vsum(sq) / Val((Scalar)x.size());
 auto scale = (ms + Val(Scalar{1e-5})).pow(Scalar{-0.5});
 auto out = Vector{};
 out.reserve(x.size());
 for (const auto& xi : x) out.push_back(xi * scale);
 return out;
}

// ---------------------------------------------------------------------------
// Globals: hyperparameters, vocab, parameters.
// ---------------------------------------------------------------------------
auto n_layer = 1; // depth of the transformer (number of layers)
auto n_embd = 16; // width of the network (embedding dimension)
auto block_size = 16; // maximum context length
auto n_head = 4; // number of attention heads
auto head_dim = 0; // derived: n_embd / n_head
auto vocab_size = 0;
auto BOS = 0;
auto uchars = Chars{};
auto state_dict = Dict{};
auto params = std::vector<Val>{};

auto layer_key(int li, const char* name) -> std::string {
 return "layer" + std::to_string(li) + "." + name;
}

auto rng = std::mt19937{42};

auto make_matrix(int nout, int nin, Scalar std = 0.08) -> Matrix {
 auto dist = std::normal_distribution<Scalar>{Scalar{0}, std};
 auto m = Matrix(nout, Vector(nin));
 for (auto& row : m)
 std::ranges::generate(row, [&] { return Val(dist(rng)); });
 return m;
}

auto gpt(int token_id, int pos_id, KVCache& keys, KVCache& values) -> Vector {
 auto x = Vector(n_embd);
 for (auto i : std::views::iota(0, n_embd))
 x[i] = state_dict["wte"][token_id][i] + state_dict["wpe"][pos_id][i];
 x = rmsnorm(x); // not redundant due to backward pass via the residual connection

 for (auto li : std::views::iota(0, n_layer)) {
 // 1) Multi-head attention block
 auto x_residual = x;
 x = rmsnorm(x);
 auto q = linear(x, state_dict[layer_key(li, "attn_wq")]);
 auto k = linear(x, state_dict[layer_key(li, "attn_wk")]);
 auto v = linear(x, state_dict[layer_key(li, "attn_wv")]);
 keys[li].push_back(k);
 values[li].push_back(v);
 auto x_attn = Vector{};
 x_attn.reserve(n_embd);
 auto T = (int)keys[li].size();
 for (auto h : std::views::iota(0, n_head)) {
 auto hs = h * head_dim;
 auto attn_logits = Vector{};
 attn_logits.reserve(T);
 for (auto t : std::views::iota(0, T)) {
 auto s = Val(Scalar{0});
 for (auto j : std::views::iota(0, head_dim))
 s = s + q[hs + j] * keys[li][t][hs + j];
 attn_logits.push_back(s / Val(std::sqrt((Scalar)head_dim)));
 }
 auto attn_weights = softmax(attn_logits);
 auto head_out = Vector(head_dim, Val(Scalar{0}));
 for (auto t : std::views::iota(0, T))
 for (auto j : std::views::iota(0, head_dim))
 head_out[j] = head_out[j] + attn_weights[t] * values[li][t][hs + j];
 std::ranges::copy(head_out, std::back_inserter(x_attn));
 }
 x = linear(x_attn, state_dict[layer_key(li, "attn_wo")]);
 for (auto i : std::views::iota(0, n_embd))
 x[i] = x[i] + x_residual[i];

 // 2) MLP block
 x_residual = x;
 x = rmsnorm(x);
 x = linear(x, state_dict[layer_key(li, "mlp_fc1")]);
 std::ranges::transform(x, x.begin(), [](const auto& xi) { return xi.relu(); });
 x = linear(x, state_dict[layer_key(li, "mlp_fc2")]);
 for (auto i : std::views::iota(0, n_embd))
 x[i] = x[i] + x_residual[i];
 }
 return linear(x, state_dict["lm_head"]);
}

// ---------------------------------------------------------------------------
// Dataset: fetch names.txt via curl/wget if not present.
// ---------------------------------------------------------------------------
auto ensure_dataset(const std::string& path) -> void {
 if (std::filesystem::exists(path)) return;
 auto url = std::string{"https://raw.githubusercontent.com/karpathy/makemore/988aa59/names.txt"};
 std::cout << "downloading " << url << " ...\n";
 auto cmd = "curl -fsSL '" + url + "' -o '" + path +
 "' || wget -q '" + url + "' -O '" + path + "'";
 if (std::system(cmd.c_str()) != 0 || !std::filesystem::exists(path)) {
 std::cerr << "could not fetch dataset; please download " << url
 << " and save it as " << path << "\n";
 std::exit(1);
 }
}

auto main() -> int {
 // Let there be a Dataset `docs`: list of documents (e.g. a list of names)
 ensure_dataset("input.txt");
 auto docs = std::vector<std::string>{};
 {
 auto f = std::ifstream{"input.txt"};
 auto line = std::string{};
 while (std::getline(f, line)) {
 while (!line.empty() && (line.back() == '\r' || line.back() == '\n' || line.back() == ' '))
 line.pop_back();
 if (!line.empty()) docs.push_back(line);
 }
 }
 std::ranges::shuffle(docs, rng);
 std::cout << "num docs: " << docs.size() << "\n";

 // Let there be a Tokenizer to translate strings to sequences of integers and back
 {
 auto seen = std::unordered_set<char>{};
 for (const auto& d : docs)
 for (auto c : d) seen.insert(c);
 uchars.assign(seen.begin(), seen.end());
 std::ranges::sort(uchars);
 }
 BOS = (int)uchars.size(); // Beginning of Sequence special token
 vocab_size = (int)uchars.size() + 1; // +1 for BOS
 std::cout << "vocab size: " << vocab_size << "\n";

 auto char_to_id = [](char c) -> int {
 return (int)(std::ranges::lower_bound(uchars, c) - uchars.begin());
 };

 // Initialize the parameters, to store the knowledge of the model
 head_dim = n_embd / n_head;
 state_dict["wte"] = make_matrix(vocab_size, n_embd);
 state_dict["wpe"] = make_matrix(block_size, n_embd);
 state_dict["lm_head"] = make_matrix(vocab_size, n_embd);
 for (auto i : std::views::iota(0, n_layer)) {
 state_dict[layer_key(i, "attn_wq")] = make_matrix(n_embd, n_embd);
 state_dict[layer_key(i, "attn_wk")] = make_matrix(n_embd, n_embd);
 state_dict[layer_key(i, "attn_wv")] = make_matrix(n_embd, n_embd);
 state_dict[layer_key(i, "attn_wo")] = make_matrix(n_embd, n_embd);
 state_dict[layer_key(i, "mlp_fc1")] = make_matrix(4 * n_embd, n_embd);
 state_dict[layer_key(i, "mlp_fc2")] = make_matrix(n_embd, 4 * n_embd);
 }
 for (auto& [name, mat] : state_dict)
 for (auto& row : mat)
 for (auto& p : row) params.push_back(p); // flatten: single list of Val
 std::cout << "num params: " << params.size() << "\n";

 // Let there be Adam, the blessed optimizer and its buffers
 auto learning_rate = Scalar{0.01};
 auto beta1 = Scalar{0.85};
 auto beta2 = Scalar{0.99};
 auto eps_adam = Scalar{1e-8};
 auto m = Weights(params.size(), Scalar{0});
 auto v = Weights(params.size(), Scalar{0});

 // Repeat in sequence
 auto num_steps = 1000;
 auto batch_size = 8; // tune: 1 = original, 8/16/32 = more stable gradients
 for (auto step : std::views::iota(0, num_steps)) {

 // Collect losses across all documents in the batch.
 // Each doc gets its own fresh KV cache (sequences are independent).
 // Gradients accumulate in the shared parameter nodes across all forward passes.
 auto all_losses = Vector{};
 for (auto b : std::views::iota(0, batch_size)) {
 // Take the next doc in round-robin, tokenize, wrap with BOS on both sides
 const auto& doc = docs[(step * batch_size + b) % docs.size()];
 auto tokens = Tokens{};
 tokens.reserve(doc.size() + 2);
 tokens.push_back(BOS);
 for (auto c : doc) tokens.push_back(char_to_id(c));
 tokens.push_back(BOS);
 auto n = std::min(block_size, (int)tokens.size() - 1);

 // Forward this document through the model
 auto keys = KVCache(n_layer);
 auto values = KVCache(n_layer);
 for (auto pos_id : std::views::iota(0, n)) {
 auto token_id = tokens[pos_id];
 auto target_id = tokens[pos_id + 1];
 auto logits = gpt(token_id, pos_id, keys, values);
 auto probs = softmax(logits);
 all_losses.push_back(-probs[target_id].log());
 }
 }

 // Average loss over every token in every document in the batch. May yours be low.
 auto loss = Val(Scalar{1} / (int)all_losses.size()) * vsum(all_losses);

 // Backward: calculate gradients w.r.t. all model parameters
 loss.backward();

 // Adam optimizer update
 auto lr_t = learning_rate * (Scalar{1} - (Scalar)step / num_steps); // linear LR decay
 for (auto i : std::views::iota(0u, params.size())) {
 auto g = params[i].grad();
 m[i] = beta1 * m[i] + (Scalar{1} - beta1) * g;
 v[i] = beta2 * v[i] + (Scalar{1} - beta2) * g * g;
 auto m_hat = m[i] / (Scalar{1} - std::pow(beta1, (Scalar)(step + 1)));
 auto v_hat = v[i] / (Scalar{1} - std::pow(beta2, (Scalar)(step + 1)));
 params[i].set_data(params[i].data() - lr_t * m_hat / (std::sqrt(v_hat) + eps_adam));
 params[i].zero_grad();
 }

 std::cout << "step " << (step + 1) << " / " << num_steps
 << " | batch " << batch_size
 << " | loss " << loss.data() << "\r" << std::flush;
 }

 // Inference: may the model babble back to us
 auto temperature = Scalar{0.5}; // in (0,1], low = conservative, high = creative
 std::cout << "\n--- inference (new, hallucinated names) ---\n";
 for (auto sample_idx : std::views::iota(0, 20)) {
 auto keys = KVCache(n_layer);
 auto values = KVCache(n_layer);
 auto token_id = BOS;
 auto sample = std::string{};
 for (auto pos_id : std::views::iota(0, block_size)) {
 auto logits = gpt(token_id, pos_id, keys, values);
 auto scaled = Vector{};
 scaled.reserve(logits.size());
 std::ranges::transform(logits, std::back_inserter(scaled),
 [temperature](const auto& l) { return l / Val(temperature); });
 auto probs = softmax(scaled);
 auto weights = Weights{};
 weights.reserve(probs.size());
 std::ranges::transform(probs, std::back_inserter(weights),
 [](const auto& p) { return p.data(); });
 auto dist = std::discrete_distribution<int>{weights.begin(), weights.end()};
 token_id = dist(rng);
 if (token_id == BOS) break;
 sample.push_back(uchars[token_id]);
 }
 std::cout << "sample " << (sample_idx + 1) << ": " << sample << "\n";
 }
 return 0;
}
