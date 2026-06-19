/// @file    gpt.cpp
/// @brief   Pure C++23 GPT: autograd → transformer → training → inference.
///          Zero dependencies beyond the standard library.
/// @details The entire learning algorithm in a single translation unit:
///          reverse-mode autograd on scalar computation graphs, a small
///          decoder-only transformer with multi-head self-attention, Adam
///          optimisation, character-level tokenisation, and ancestral
///          sampling at inference time.
/// @style   AAA, trailing return types, std::ranges, concept-constrained
///          templates, snake_case for template classes.

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

// ============================================================================
// 1. Numeric concept
// ============================================================================

/// @brief Constrains a type to behave as a scalar real number.
/// @tparam T  Candidate type – must be floating-point or integral.
template<typename T>
concept Number = std::floating_point<T> || std::integral<T>;

// ============================================================================
// 2. Autograd
// ============================================================================

/// @brief Node in the scalar computation graph.
/// @tparam ScalarT  Underlying numeric scalar type (must satisfy Number).
///
/// Each node stores its data and accumulated grad, plus the children
/// and local gradients needed for reverse-mode automatic differentiation.
template<Number ScalarT>
struct value_node {
  using scalar    = ScalarT;                        ///< Exposed scalar alias.
  using node_ptr  = std::shared_ptr<value_node>;    ///< Heap-allocated node.
  using children  = std::vector<node_ptr>;           ///< Dependency list.
  using gradients = std::vector<scalar>;             ///< Local gradient buffer.

  scalar   data;                                     ///< Forward value.
  scalar   grad = scalar{0};                         ///< Accumulated gradient.
  children children_list = {};                       ///< Operands in the graph.
  gradients local_grads = {};                        ///< d(this) / d(child).

  /// Leaf value constructor.
  explicit value_node(scalar d) : data(d) {}

  /// Internal node: value + children + local gradients.
  value_node(scalar d, children ch, gradients lg)
    : data(d), children_list(std::move(ch)), local_grads(std::move(lg)) {}
};

/// @brief User-facing wrapper that builds the graph via operator overloads.
/// @tparam ScalarT  Underlying numeric scalar type.
///
/// Arithmetic operators (+, *, -, /, pow, log, exp, relu) produce new value
/// nodes wired into the computation graph.  Call backward() to run
/// reverse-mode automatic differentiation.
template<Number ScalarT>
class value {
public:
  using scalar   = ScalarT;
  using node     = value_node<scalar>;
  using node_ptr = std::shared_ptr<node>;

  node_ptr ptr;                                     ///< Owning reference.

  /// Construct a leaf value.
  explicit value(scalar d = scalar{0})
    : ptr(std::make_shared<node>(d)) {}

  /// Wrap an existing node (used internally by arithmetic).
  explicit value(node_ptr n) : ptr(std::move(n)) {}

  /// @name Data access
  ///@{
  [[nodiscard]] auto data()     const -> scalar { return ptr->data; }
  [[nodiscard]] auto grad()     const -> scalar { return ptr->grad; }
  auto set_data(scalar d)             -> void  { ptr->data = d; }
  auto zero_grad()                    -> void  { ptr->grad = scalar{0}; }
  ///@}

  // ── Arithmetic operators ─────────────────────────────────────────────

  /// @brief Element-wise addition.
  [[nodiscard]] auto operator+(const value& o) const -> value {
    return value(std::make_shared<node>(
      ptr->data + o.ptr->data,
      typename node::children{ptr, o.ptr},
      typename node::gradients{scalar{1}, scalar{1}}));
  }

  /// @brief Element-wise multiplication.
  [[nodiscard]] auto operator*(const value& o) const -> value {
    return value(std::make_shared<node>(
      ptr->data * o.ptr->data,
      typename node::children{ptr, o.ptr},
      typename node::gradients{o.ptr->data, ptr->data}));
  }

  /// @brief Power: this ** p.
  [[nodiscard]] auto pow(scalar p) const -> value {
    auto out = std::pow(ptr->data, p);
    return value(std::make_shared<node>(
      out,
      typename node::children{ptr},
      typename node::gradients{
        p * std::pow(ptr->data, p - scalar{1})}));
  }

  /// @brief Natural logarithm.
  [[nodiscard]] auto log() const -> value {
    return value(std::make_shared<node>(
      std::log(ptr->data),
      typename node::children{ptr},
      typename node::gradients{scalar{1} / ptr->data}));
  }

  /// @brief Exponential function.
  [[nodiscard]] auto exp() const -> value {
    auto e = std::exp(ptr->data);
    return value(std::make_shared<node>(
      e,
      typename node::children{ptr},
      typename node::gradients{e}));
  }

  /// @brief Rectified linear unit.
  [[nodiscard]] auto relu() const -> value {
    auto out = std::max(scalar{0}, ptr->data);
    return value(std::make_shared<node>(
      out,
      typename node::children{ptr},
      typename node::gradients{
        ptr->data > scalar{0} ? scalar{1} : scalar{0}}));
  }

  [[nodiscard]] auto operator-()  const -> value { return *this * value(scalar{-1}); }
  [[nodiscard]] auto operator-(const value& o) const -> value { return *this + (-o); }
  [[nodiscard]] auto operator/(const value& o) const -> value { return *this * o.pow(scalar{-1}); }

  // ── Backpropagation ──────────────────────────────────────────────────

  /// @brief Run reverse-mode automatic differentiation.
  ///
  /// Performs a topological sort of the computation graph starting at this
  /// node, then applies the chain rule in reverse order to accumulate
  /// gradients into every ancestor node.
  auto backward() -> void {
    auto topo    = std::vector<node_ptr>{};
    auto visited = std::unordered_set<node*>{};

    auto build = std::function<void(const node_ptr&)>{};
    build = [&](const auto& v) {
      if (visited.insert(v.get()).second) {
        for (const auto& c : v->children_list) build(c);
        topo.push_back(v);
      }
    };
    build(ptr);

    ptr->grad = scalar{1};
    for (const auto& v : topo | std::views::reverse)
      for (auto i : std::views::iota(0u, v->children_list.size()))
        v->children_list[i]->grad += v->local_grads[i] * v->grad;
  }
};

// ============================================================================
// 3. Concrete type aliases
// ============================================================================

using scalar   = double;                            ///< Default numeric type.
using val      = value<scalar>;                     ///< Autograd value.
using vector   = std::vector<val>;                  ///< Autograd vector.
using matrix   = std::vector<vector>;               ///< Weight matrix.
using weights  = std::vector<scalar>;               ///< Raw float buffer.
using tokens   = std::vector<int>;                  ///< Token sequence.
using chars    = std::vector<char>;                 ///< Character vocabulary.
using kv_cache = std::vector<std::vector<vector>>;  ///< [layer][time]->embedding.
using dict     = std::unordered_map<std::string, matrix>;

// ============================================================================
// 4. Generic vector utilities
// ============================================================================

/// @brief Sum all elements of a vector using range-based fold.
/// @param xs  Input vector of autograd values.
/// @return    A single val equal to the element-wise sum.
[[nodiscard]] auto vsum(const vector& xs) -> val {
  return std::ranges::fold_left(xs, val{}, std::plus<>{});
}

// ============================================================================
// 5. Model operations
// ============================================================================

/// @brief Linear (fully-connected) layer: x @ W^T.
/// @param x  Input vector of size nin.
/// @param w  Weight matrix of shape (nout, nin).
/// @return   Output vector of size nout.
[[nodiscard]] auto linear(const vector& x, const matrix& w) -> vector {
  auto out = vector{}; out.reserve(w.size());

  /// Compute a single row of the output: dot product of x with one row.
  auto dot_row = [&x](const vector& row) -> val {
    return std::ranges::fold_left(
      std::views::zip(row, x) | std::views::transform(
        [](const auto& p) -> val {
          const auto& [a, b] = p;
          return a * b;
        }),
      val{}, std::plus<>{});
  };

  std::ranges::transform(w, std::back_inserter(out), dot_row);
  return out;
}

/// @brief Softmax normalisation: exp(x_i - max) / sum(exp(...)).
/// @param logits  Raw score vector.
/// @return        Probability distribution (same size, sums to 1).
[[nodiscard]] auto softmax(const vector& logits) -> vector {
  auto max_val = std::ranges::max(
    logits | std::views::transform(&val::data));

  auto exps = vector{}; exps.reserve(logits.size());
  std::ranges::transform(logits, std::back_inserter(exps),
    [max_val](const auto& v) { return (v - val(max_val)).exp(); });

  auto total = vsum(exps);
  auto out   = vector{}; out.reserve(exps.size());
  std::ranges::transform(exps, std::back_inserter(out),
    [&total](const auto& e) { return e / total; });

  return out;
}

/// @brief RMS normalisation: x / sqrt(mean(x^2) + epsilon).
/// @param x  Input vector.
/// @return   Normalised vector (same size).
[[nodiscard]] auto rmsnorm(const vector& x) -> vector {
  auto sq = vector{}; sq.reserve(x.size());
  std::ranges::transform(x, std::back_inserter(sq),
    [](const auto& xi) { return xi * xi; });

  auto ms    = vsum(sq) / val(static_cast<scalar>(x.size()));
  auto scale = (ms + val(scalar{1e-5})).pow(scalar{-0.5});

  auto out = vector{}; out.reserve(x.size());
  std::ranges::transform(x, std::back_inserter(out),
    [&scale](const auto& xi) { return xi * scale; });

  return out;
}

// ============================================================================
// 6. Global state (model hyper-parameters, vocabulary, buffers)
// ============================================================================

auto n_layer    = 1;          ///< Transformer depth.
auto n_embd     = 16;         ///< Embedding dimension.
auto block_size = 16;         ///< Maximum context length.
auto n_head     = 4;          ///< Number of attention heads.
auto head_dim   = 0;          ///< Derived: n_embd / n_head.
auto vocab_size = 0;          ///< Vocabulary cardinality.
auto BOS        = 0;          ///< Beginning-of-sequence token id.
auto uchars     = chars{};    ///< Sorted unique characters.
auto state_dict = dict{};     ///< Layer weights indexed by name.
auto params     = std::vector<val>{};  ///< Flat parameter list.

/// @brief Build a state-dict key for layer li and weight name.
auto layer_key(int li, const char* name) -> std::string {
  return "layer" + std::to_string(li) + "." + name;
}

/// Deterministic random engine (seed chosen for reproducibility).
auto rng = std::mt19937{42};

/// @brief Create a weight matrix initialised with a normal distribution.
/// @param nout  Number of rows (output dimension).
/// @param nin   Number of columns (input dimension).
/// @param stdv  Standard deviation of the init distribution.
[[nodiscard]] auto make_matrix(int nout, int nin, scalar stdv = 0.08) -> matrix {
  auto dist = std::normal_distribution<scalar>{scalar{0}, stdv};
  auto m = matrix(nout, vector(nin));
  for (auto& row : m)
    std::ranges::generate(row, [&] { return val(dist(rng)); });
  return m;
}

// ============================================================================
// 7. Forward pass: a small decoder-only transformer
// ============================================================================

/// @brief Run one forward step of the transformer.
/// @param token_id  Current input token.
/// @param pos_id    Position in the sequence.
/// @param keys      KV-cache for keys   (mutated in-place).
/// @param values    KV-cache for values (mutated in-place).
/// @return          Logit vector over the vocabulary.
///
/// Architecture (single layer):
///   token + position embedding -> rmsnorm -> multi-head self-attention
///   -> residual add -> rmsnorm -> ReLU MLP -> residual add -> lm_head
[[nodiscard]] auto gpt(int token_id, int pos_id, kv_cache& keys,
                       kv_cache& values) -> vector {
  // ── Embedding ──
  auto x = vector(n_embd);
  std::ranges::transform(
    state_dict["wte"][token_id],
    state_dict["wpe"][pos_id],
    x.begin(), std::plus<>{});
  x = rmsnorm(x);

  for (auto li : std::views::iota(0, n_layer)) {
    // ── Multi-head self-attention ──
    auto x_residual = x;
    x = rmsnorm(x);

    auto q = linear(x, state_dict[layer_key(li, "attn_wq")]);
    auto k = linear(x, state_dict[layer_key(li, "attn_wk")]);
    auto v = linear(x, state_dict[layer_key(li, "attn_wv")]);
    keys[li].push_back(k);
    values[li].push_back(v);

    auto x_attn = vector{}; x_attn.reserve(n_embd);
    auto T      = (int)keys[li].size();

    for (auto h : std::views::iota(0, n_head)) {
      auto hs = h * head_dim;

      // Scaled dot-product attention scores across all time steps
      auto attn_logits = vector{}; attn_logits.reserve(T);
      for (auto t : std::views::iota(0, T)) {
        auto s = std::ranges::fold_left(
          std::views::iota(0, head_dim) | std::views::transform(
            [&](int j) { return q[hs + j] * keys[li][t][hs + j]; }),
          val{}, std::plus<>{});
        attn_logits.push_back(s / val(std::sqrt(scalar(head_dim))));
      }

      auto attn_weights = softmax(attn_logits);

      // Weighted sum of values
      auto head_out = vector(head_dim, val{});
      for (auto t : std::views::iota(0, T))
        for (auto j : std::views::iota(0, head_dim))
          head_out[j] = head_out[j] + attn_weights[t] * values[li][t][hs + j];

      std::ranges::copy(head_out, std::back_inserter(x_attn));
    }

    x = linear(x_attn, state_dict[layer_key(li, "attn_wo")]);
    std::ranges::transform(x, x_residual, x.begin(), std::plus<>{});

    // ── MLP block ──
    x_residual = x;
    x = rmsnorm(x);
    x = linear(x, state_dict[layer_key(li, "mlp_fc1")]);
    std::ranges::for_each(x, [](val& xi) { xi = xi.relu(); });
    x = linear(x, state_dict[layer_key(li, "mlp_fc2")]);
    std::ranges::transform(x, x_residual, x.begin(), std::plus<>{});
  }

  return linear(x, state_dict["lm_head"]);
}

// ============================================================================
// 8. Dataset loading
// ============================================================================

/// @brief Download Karpathy's names.txt if not already present locally.
/// @param path  Local file path.
///
/// Tries curl first, then wget.  Prints an error and aborts if both fail.
auto ensure_dataset(const std::string& path) -> void {
  if (std::filesystem::exists(path)) return;

  static constexpr auto url =
    "https://raw.githubusercontent.com/karpathy/makemore/988aa59/names.txt";

  std::cout << "⬇️  downloading " << url << " ...\n";
  auto cmd = "curl -fsSL '" + std::string(url) + "' -o '" + path +
    "' || wget -q '" + std::string(url) + "' -O '" + path + "'";

  if (std::system(cmd.c_str()) != 0 || !std::filesystem::exists(path)) {
    std::cerr << "❌ could not fetch dataset. download manually:\n"
              << "  " << url << "\n  -> " << path << "\n";
    std::exit(1);
  }
}

// ============================================================================
// 9. Entry point: train a character-level GPT on a list of names
// ============================================================================

/// @brief Train a tiny GPT and generate synthetic names.
///
/// Steps:
///   1. Load and shuffle the dataset.
///   2. Build a character-level vocabulary.
///   3. Initialise weights with a normal distribution.
///   4. Run Adam-optimised training for 1000 steps.
///   5. Sample 20 novel names via ancestral sampling.
auto main() -> int {
  std::cout << "🧠 GPT — pure C++23 autograd transformer\n\n";

  // ── Load dataset ───────────────────────────────────────────────────
  ensure_dataset("input.txt");

  auto docs = std::vector<std::string>{};
  {
    auto f    = std::ifstream{"input.txt"};
    auto line = std::string{};
    while (std::getline(f, line)) {
      while (!line.empty() &&
             (line.back() == '\r' || line.back() == '\n' || line.back() == ' '))
        line.pop_back();
      if (!line.empty()) docs.push_back(line);
    }
  }
  std::ranges::shuffle(docs, rng);
  std::cout << "📚 docs: " << docs.size() << "\n";

  // ── Build char-level tokeniser ─────────────────────────────────────
  {
    auto seen = std::unordered_set<char>{};
    for (const auto& d : docs)
      std::ranges::for_each(d, [&seen](char c) { seen.insert(c); });

    uchars.assign(seen.begin(), seen.end());
    std::ranges::sort(uchars);
  }

  BOS        = (int)uchars.size();
  vocab_size = (int)uchars.size() + 1;
  std::cout << "🔤 vocab size: " << vocab_size << "\n";

  auto char_to_id = [](char c) -> int {
    return (int)(std::ranges::lower_bound(uchars, c) - uchars.begin());
  };

  // ── Initialise weights ─────────────────────────────────────────────
  head_dim = n_embd / n_head;

  state_dict["wte"]     = make_matrix(vocab_size, n_embd);
  state_dict["wpe"]     = make_matrix(block_size, n_embd);
  state_dict["lm_head"] = make_matrix(vocab_size, n_embd);

  for (auto i : std::views::iota(0, n_layer)) {
    auto key = [i](const char* name) { return layer_key(i, name); };
    state_dict[key("attn_wq")] = make_matrix(n_embd, n_embd);
    state_dict[key("attn_wk")] = make_matrix(n_embd, n_embd);
    state_dict[key("attn_wv")] = make_matrix(n_embd, n_embd);
    state_dict[key("attn_wo")] = make_matrix(n_embd, n_embd);
    state_dict[key("mlp_fc1")] = make_matrix(4 * n_embd, n_embd);
    state_dict[key("mlp_fc2")] = make_matrix(n_embd, 4 * n_embd);
  }

  for (auto& [name, mat] : state_dict)
    for (auto& row : mat)
      for (auto& p : row) params.push_back(p);

  std::cout << "⚙️  params: " << params.size() << "\n";

  // ── Adam optimiser state ───────────────────────────────────────────
  auto learning_rate = scalar{0.01};
  auto beta1         = scalar{0.85};
  auto beta2         = scalar{0.99};
  auto eps           = scalar{1e-8};

  auto adam_m = weights(params.size(), scalar{0});
  auto adam_v = weights(params.size(), scalar{0});

  // ── Training loop ──────────────────────────────────────────────────
  auto num_steps  = 1000;
  auto batch_size = 8;

  std::cout << "\n🏋️  training " << num_steps << " steps (batch="
            << batch_size << ")...\n\n";

  for (auto step : std::views::iota(0, num_steps)) {
    // Forward & accumulate gradients over the batch
    auto all_losses = vector{};
    for (auto b : std::views::iota(0, batch_size)) {
      const auto& doc = docs[(step * batch_size + b) % docs.size()];

      auto toks = tokens{}; toks.reserve(doc.size() + 2);
      toks.push_back(BOS);
      std::ranges::transform(doc, std::back_inserter(toks), char_to_id);
      toks.push_back(BOS);

      auto n      = std::min(block_size, (int)toks.size() - 1);
      auto keys   = kv_cache(n_layer);
      auto values = kv_cache(n_layer);

      for (auto pos_id : std::views::iota(0, n)) {
        auto logits = gpt(toks[pos_id], pos_id, keys, values);
        auto probs  = softmax(logits);
        all_losses.push_back(-probs[toks[pos_id + 1]].log());
      }
    }

    auto loss = val(scalar{1} / scalar(all_losses.size())) * vsum(all_losses);
    loss.backward();

    // Adam parameter update
    auto lr_t = learning_rate * (scalar{1} - scalar(step) / scalar(num_steps));
    for (auto i : std::views::iota(0u, params.size())) {
      auto g = params[i].grad();

      adam_m[i] = beta1 * adam_m[i] + (scalar{1} - beta1) * g;
      adam_v[i] = beta2 * adam_v[i] + (scalar{1} - beta2) * g * g;

      auto m_hat = adam_m[i] / (scalar{1} - std::pow(beta1, scalar(step + 1)));
      auto v_hat = adam_v[i] / (scalar{1} - std::pow(beta2, scalar(step + 1)));

      params[i].set_data(
        params[i].data() - lr_t * m_hat / (std::sqrt(v_hat) + eps));
      params[i].zero_grad();
    }

    std::cout << "  step " << (step + 1) << "/" << num_steps
              << "  loss " << loss.data() << "\r" << std::flush;
  }

  // ── Inference: generate new names ──────────────────────────────────
  auto temperature = scalar{0.5};
  std::cout << "\n\n✨ generating names...\n\n";

  for (auto i : std::views::iota(0, 20)) {
    auto keys    = kv_cache(n_layer);
    auto values  = kv_cache(n_layer);
    auto token_id = BOS;
    auto sample   = std::string{};

    for (auto pos_id : std::views::iota(0, block_size)) {
      auto logits = gpt(token_id, pos_id, keys, values);

      auto scaled = vector{}; scaled.reserve(logits.size());
      std::ranges::transform(logits, std::back_inserter(scaled),
        [temperature](const auto& l) { return l / val(temperature); });

      auto probs   = softmax(scaled);
      auto wghts = weights{}; wghts.reserve(probs.size());
      std::ranges::transform(probs, std::back_inserter(wghts),
        [](const auto& p) { return p.data(); });

      token_id = std::discrete_distribution<int>{
        wghts.begin(), wghts.end()}(rng);

      if (token_id == BOS) break;
      sample.push_back(uchars[token_id]);
    }

    std::cout << "  " << (i + 1) << ". " << sample << "\n";
  }

  std::cout << "\n✅ done.\n";
  return 0;
}
