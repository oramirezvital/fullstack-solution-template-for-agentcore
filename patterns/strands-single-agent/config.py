"""Configuration management for Investment Advisor agent."""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class AgentConfig:
    """
    Configuration for Investment Advisor agent.
    
    This class centralizes all configuration management and validation,
    ensuring that required environment variables are present and valid
    before the agent starts processing requests.
    
    Attributes:
        memory_id: AgentCore Memory resource ID for conversation history
        stack_name: CloudFormation stack name for resource lookups
        aws_region: AWS region for service calls
        gateway_url: Optional AgentCore Gateway URL for MCP tools
    """
    
    memory_id: str
    stack_name: str
    aws_region: str
    gateway_url: Optional[str] = None
    
    @classmethod
    def from_environment(cls) -> "AgentConfig":
        """
        Load configuration from environment variables with validation.
        
        This method reads configuration from environment variables set by
        the CDK deployment and validates that all required values are present.
        It's designed to fail fast at startup rather than during request processing.
        
        Returns:
            AgentConfig: Validated configuration instance
            
        Raises:
            ValueError: If required environment variables are missing or invalid
        """
        memory_id = os.environ.get("MEMORY_ID")
        if not memory_id:
            raise ValueError(
                "MEMORY_ID environment variable is required. "
                "This should be set by the CDK deployment in backend-stack.ts"
            )
        
        stack_name = os.environ.get("STACK_NAME")
        if not stack_name:
            raise ValueError(
                "STACK_NAME environment variable is required. "
                "This should be set by the CDK deployment in backend-stack.ts"
            )
        
        aws_region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        gateway_url = os.environ.get("GATEWAY_URL")
        
        config = cls(
            memory_id=memory_id,
            stack_name=stack_name,
            aws_region=aws_region,
            gateway_url=gateway_url,
        )
        
        # Validate configuration values
        config.validate()
        
        return config
    
    def validate(self) -> None:
        """
        Validate configuration values for correctness.
        
        This method performs additional validation beyond presence checks,
        ensuring that values are not just present but also valid.
        
        Raises:
            ValueError: If configuration values are invalid
        """
        if not self.memory_id.strip():
            raise ValueError("MEMORY_ID cannot be empty or whitespace")
        
        if not self.stack_name.strip():
            raise ValueError("STACK_NAME cannot be empty or whitespace")
        
        if not self.aws_region.strip():
            raise ValueError("AWS_DEFAULT_REGION cannot be empty or whitespace")
        
        # Validate region format (basic check)
        if not self.aws_region.replace("-", "").replace("_", "").isalnum():
            raise ValueError(f"Invalid AWS region format: {self.aws_region}")
