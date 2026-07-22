from abc import ABC, abstractmethod

from src.models.readings import EnergyReading


class CollectorBase(ABC):
    """Base class for all energy source collectors.

    Each collector fetches a single reading from one device.
    Implement fetch() to return a validated EnergyReading subclass.
    """

    @abstractmethod
    def fetch(self) -> EnergyReading:
        """Fetch the latest reading from the device.

        Raises:
            ConnectionError: when the device is unreachable after retries.
            ValueError: when the response cannot be parsed or validated.
        """
        ...
