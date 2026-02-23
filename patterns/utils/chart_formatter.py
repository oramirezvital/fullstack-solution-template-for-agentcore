"""
Chart Data Formatter Utility

This module provides utilities for formatting and validating chart data
that will be rendered in the frontend using React charting libraries.

The agent returns chart data as structured JSON, and the frontend
renders it using Recharts or similar libraries.

Author: Investment Advisor Agent Team
"""

from typing import Dict, Any, List, Literal, Optional
from pydantic import BaseModel, Field, validator


ChartType = Literal["line", "bar", "area", "pie", "doughnut"]


class ChartDataset(BaseModel):
    """
    Represents a single dataset in a chart.
    
    Attributes:
        label: Name of the dataset (e.g., "AMZN Price")
        data: Array of numeric values
        color: Hex color code for the dataset (e.g., "#3fb950")
    """
    label: str = Field(..., description="Dataset label")
    data: List[float] = Field(..., description="Array of numeric values")
    color: str = Field(default="#3fb950", description="Hex color code")
    
    @validator('color')
    def validate_color(cls, v: str) -> str:
        """Validate that color is a valid hex code."""
        if not v.startswith('#') or len(v) not in [4, 7]:
            raise ValueError(f"Invalid hex color: {v}")
        return v


class ChartData(BaseModel):
    """
    Represents the data structure for a chart.
    
    Attributes:
        labels: Array of x-axis labels
        datasets: Array of datasets to plot
    """
    labels: List[str] = Field(..., description="X-axis labels")
    datasets: List[ChartDataset] = Field(..., description="Chart datasets")
    
    @validator('labels')
    def validate_labels(cls, v: List[str]) -> List[str]:
        """Ensure labels array is not empty."""
        if not v:
            raise ValueError("Labels array cannot be empty")
        return v
    
    @validator('datasets')
    def validate_datasets(cls, v: List[ChartDataset]) -> List[ChartDataset]:
        """Ensure datasets array is not empty."""
        if not v:
            raise ValueError("Datasets array cannot be empty")
        return v


class ChartOptions(BaseModel):
    """
    Optional chart configuration.
    
    Attributes:
        yAxisLabel: Label for Y-axis
        xAxisLabel: Label for X-axis
        showLegend: Whether to show legend
        showGrid: Whether to show grid lines
    """
    yAxisLabel: Optional[str] = Field(None, description="Y-axis label")
    xAxisLabel: Optional[str] = Field(None, description="X-axis label")
    showLegend: bool = Field(default=True, description="Show legend")
    showGrid: bool = Field(default=True, description="Show grid lines")


class ChartSpec(BaseModel):
    """
    Complete chart specification that the agent returns.
    
    This is the JSON structure that the agent includes in its response,
    which the frontend detects and renders as an interactive chart.
    
    Attributes:
        type: Always "chart" to identify this as chart data
        chartType: Type of chart to render
        title: Chart title
        data: Chart data (labels and datasets)
        options: Optional chart configuration
    """
    type: Literal["chart"] = Field(default="chart", description="Type identifier")
    chartType: ChartType = Field(..., description="Chart type")
    title: str = Field(..., description="Chart title")
    data: ChartData = Field(..., description="Chart data")
    options: Optional[ChartOptions] = Field(None, description="Chart options")


def create_chart_spec(
    chart_type: ChartType,
    title: str,
    labels: List[str],
    datasets: List[Dict[str, Any]],
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a validated chart specification.
    
    This function validates the chart data and returns a JSON-serializable
    dictionary that can be included in the agent's response.
    
    Args:
        chart_type: Type of chart ("line", "bar", "area", "pie", "doughnut")
        title: Chart title
        labels: Array of x-axis labels
        datasets: Array of dataset dictionaries with 'label', 'data', and optional 'color'
        options: Optional chart configuration
        
    Returns:
        Dict containing validated chart specification
        
    Raises:
        ValueError: If chart data is invalid
        
    Example:
        >>> spec = create_chart_spec(
        ...     chart_type="line",
        ...     title="Amazon Stock Price",
        ...     labels=["Feb 11", "Feb 12", "Feb 13"],
        ...     datasets=[{
        ...         "label": "AMZN Price (USD)",
        ...         "data": [204.08, 199.6, 198.79],
        ...         "color": "#3fb950"
        ...     }]
        ... )
    """
    # Build chart spec
    chart_spec = ChartSpec(
        type="chart",
        chartType=chart_type,
        title=title,
        data=ChartData(
            labels=labels,
            datasets=[ChartDataset(**ds) for ds in datasets]
        ),
        options=ChartOptions(**options) if options else None
    )
    
    # Return as dictionary for JSON serialization
    return chart_spec.model_dump(exclude_none=True)


def format_chart_json(chart_spec: Dict[str, Any]) -> str:
    """
    Format chart specification as a JSON code block for agent response.
    
    The agent should include this in its response so the frontend
    can detect and render it as a chart.
    
    Args:
        chart_spec: Chart specification dictionary from create_chart_spec()
        
    Returns:
        Formatted JSON string wrapped in markdown code block
        
    Example:
        >>> spec = create_chart_spec(...)
        >>> json_block = format_chart_json(spec)
        >>> print(json_block)
        ```json
        {
          "type": "chart",
          "chartType": "line",
          ...
        }
        ```
    """
    import json
    json_str = json.dumps(chart_spec, indent=2)
    return f"```json\n{json_str}\n```"
