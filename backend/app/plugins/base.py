from abc import ABC, abstractmethod
from typing import Dict, Any

class IntelligencePlugin(ABC):
    """Abstract base class for Intelligence Plugins."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name of the plugin."""
        pass

    @abstractmethod
    async def analyze(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze incoming data and return insights.
        
        Args:
            data: The input telemetry or entity data.
            
        Returns:
            A dictionary containing the analysis results.
        """
        pass
