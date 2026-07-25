# ====================================================================================================
# Credit Model Abstraction
# ====================================================================================================

"""
Credit Model Abstraction — strategy pattern for different provider credit policies.

Supports:
  - ONE_TIME: Fixed credit that does not refresh
  - MONTHLY_RESET: Monthly budget that resets to the configured amount each cycle (non-cumulative)

Extensible: add new credit models by implementing CreditModelStrategy.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class CreditModelType(str, Enum):
    """Types of credit models for providers."""
    ONE_TIME    = "one_time"      # Fixed credit, no refresh
    MONTHLY_RESET = "monthly_reset"  # Resets to budget_amount each month (non-cumulative)


@dataclass
class CreditState:
    """
    Runtime state for a provider credit model.

    Attributes:
        budget_amount   : The configured budget amount for this provider
        budget_spent    : Total amount spent since last reset (or since creation)
        budget_used     : Amount currently available (calculated)
        last_reset_at   : Timestamp of the last reset (or creation)
        credit_model    : The credit model type
    """
    budget_amount: int
    budget_spent: int
    last_reset_at: datetime
    credit_model: CreditModelType

    @property
    def budget_available(self) -> int:
        """Return available credit (budget_amount - budget_spent for reset models)."""
        if self.credit_model == CreditModelType.ONE_TIME:
            return max(0, self.budget_amount - self.budget_spent)
        elif self.credit_model == CreditModelType.MONTHLY_RESET:
            return max(0, self.budget_amount - self.budget_spent)
        return 0

    def can_spend(self, amount: int) -> bool:
        """Check if the provider can spend the given amount."""
        return self.budget_available >= amount


class CreditModelStrategy(ABC):
    """
    Abstract base class for credit model strategies.

    Each strategy defines how credit is managed for a provider.
    """

    @abstractmethod
    def get_credit_type(self) -> CreditModelType:
        """Return the credit model type."""
        pass

    @abstractmethod
    def check_availability(self, state: CreditState, amount: int) -> bool:
        """
        Check if the provider has enough credit.

        Args:
            state: Current credit state.
            amount: Amount to check.

        Returns:
            True if the provider can spend the amount.
        """
        pass

    @abstractmethod
    def deduct(self, state: CreditState, amount: int) -> CreditState:
        """
        Deduct credit from the provider.

        Args:
            state: Current credit state.
            amount: Amount to deduct.

        Returns:
            Updated credit state.
        """
        pass

    @abstractmethod
    def should_reset(self, state: CreditState, now: datetime) -> bool:
        """
        Check if the credit should be reset (for periodic models).

        Args:
            state: Current credit state.
            now: Current datetime.

        Returns:
            True if a reset is needed.
        """
        pass

    @abstractmethod
    def reset(self, state: CreditState) -> CreditState:
        """
        Reset the credit state to the next cycle.

        Args:
            state: Current credit state.

        Returns:
            Reset credit state.

        Note:
            For non-periodic models, this should raise or return unchanged.
        """
        pass


# ====================================================================================================
# One-Time Credit Model
# ====================================================================================================


class OneTimeCreditModel(CreditModelStrategy):
    """
    One-time credit model — fixed budget that does not refresh.

    Once depleted, the provider has no more credit unless manually replenished.
    """

    def get_credit_type(self) -> CreditModelType:
        return CreditModelType.ONE_TIME

    def check_availability(self, state: CreditState, amount: int) -> bool:
        return state.can_spend(amount)

    def deduct(self, state: CreditState, amount: int) -> CreditState:
        if not self.check_availability(state, amount):
            raise ValueError("Insufficient credit for one-time model")
        return CreditState(
            budget_amount=state.budget_amount,
            budget_spent=state.budget_spent + amount,
            last_reset_at=state.last_reset_at,
            credit_model=CreditModelType.ONE_TIME,
        )

    def should_reset(self, state: CreditState, now: datetime) -> bool:
        return False  # No reset for one-time model

    def reset(self, state: CreditState) -> CreditState:
        # No reset possible for one-time model
        return state


# ====================================================================================================
# Monthly Reset Credit Model
# ====================================================================================================


class MonthlyResetCreditModel(CreditModelStrategy):
    """
    Monthly reset credit model — budget resets to the configured amount each month.

    Non-cumulative: any unused credit at the end of the month is lost.
    """

    def get_credit_type(self) -> CreditModelType:
        return CreditModelType.MONTHLY_RESET

    def check_availability(self, state: CreditState, amount: int) -> bool:
        return state.can_spend(amount)

    def deduct(self, state: CreditState, amount: int) -> CreditState:
        if not self.check_availability(state, amount):
            raise ValueError("Insufficient credit for monthly reset model")
        return CreditState(
            budget_amount=state.budget_amount,
            budget_spent=state.budget_spent + amount,
            last_reset_at=state.last_reset_at,
            credit_model=CreditModelType.MONTHLY_RESET,
        )

    def should_reset(self, state: CreditState, now: datetime) -> bool:
        """
        Check if a month has passed since the last reset.

        Args:
            state: Current credit state.
            now: Current datetime.

        Returns:
            True if the current month is different from the reset month.
        """
        if state.last_reset_at.tzinfo is None:
            last = state.last_reset_at.replace(tzinfo=timezone.utc)
        else:
            last = state.last_reset_at

        # Reset if we're in a different month/year
        return (now.year, now.month) != (last.year, last.month)

    def reset(self, state: CreditState) -> CreditState:
        """
        Reset the budget spent to zero, keeping the same budget_amount.

        Args:
            state: Current credit state.

        Returns:
            Reset credit state with budget_spent = 0.
        """
        return CreditState(
            budget_amount=state.budget_amount,
            budget_spent=0,  # Reset: non-cumulative
            last_reset_at=datetime.now(timezone.utc),
            credit_model=CreditModelType.MONTHLY_RESET,
        )


# ====================================================================================================
# Credit Model Factory
# ====================================================================================================


class CreditModelFactory:
    """Factory to create credit model strategies by type."""

    _strategies = {
        CreditModelType.ONE_TIME: OneTimeCreditModel(),
        CreditModelType.MONTHLY_RESET: MonthlyResetCreditModel(),
    }

    @classmethod
    def get_strategy(cls, model_type: CreditModelType) -> CreditModelStrategy:
        """
        Get a credit model strategy by type.

        Args:
            model_type: The credit model type.

        Returns:
            The corresponding strategy instance.

        Raises:
            ValueError: If the model type is not registered.
        """
        strategy = cls._strategies.get(model_type)
        if not strategy:
            valid = ", ".join(k.value for k in cls._strategies.keys())
            raise ValueError(f"Unknown credit model type: {model_type}. Valid types: {valid}")
        return strategy

    @classmethod
    def register_strategy(cls, model_type: CreditModelType, strategy: CreditModelStrategy) -> None:
        """
        Register a new credit model strategy.

        Use this to add custom credit models.

        Args:
            model_type: The credit model type.
            strategy: The strategy instance.
        """
        cls._strategies[model_type] = strategy


# ====================================================================================================
# Utility Functions
# ====================================================================================================


def create_credit_state(
    budget_amount: int,
    credit_model: CreditModelType,
    last_reset_at: datetime | None = None,
) -> CreditState:
    """
    Create a new credit state.

    Args:
        budget_amount: The budget amount.
        credit_model: The credit model type.
        last_reset_at: Optional last reset timestamp. Defaults to now.

    Returns:
        A new CreditState instance.
    """
    return CreditState(
        budget_amount=budget_amount,
        budget_spent=0,
        last_reset_at=last_reset_at or datetime.now(timezone.utc),
        credit_model=credit_model,
    )


def check_credit_available(
    state: CreditState,
    amount: int,
) -> bool:
    """
    Check if a credit state has enough available credit.

    Args:
        state: The current credit state.
        amount: The amount to check.

    Returns:
        True if the amount can be spent.
    """
    strategy = CreditModelFactory.get_strategy(state.credit_model)
    return strategy.check_availability(state, amount)


def deduct_credit(
    state: CreditState,
    amount: int,
) -> CreditState:
    """
    Deduct credit from a credit state.

    Args:
        state: The current credit state.
        amount: The amount to deduct.

    Returns:
        The updated credit state.

    Raises:
        ValueError: If insufficient credit.
    """
    strategy = CreditModelFactory.get_strategy(state.credit_model)
    return strategy.deduct(state, amount)


def maybe_reset_credit(
    state: CreditState,
    now: datetime | None = None,
) -> CreditState:
    """
    Reset credit if needed based on the current model.

    Args:
        state: The current credit state.
        now: Optional current datetime. Defaults to now.

    Returns:
        The credit state (possibly reset).
    """
    now_dt = now or datetime.now(timezone.utc)
    strategy = CreditModelFactory.get_strategy(state.credit_model)

    if strategy.should_reset(state, now_dt):
        return strategy.reset(state)

    return state