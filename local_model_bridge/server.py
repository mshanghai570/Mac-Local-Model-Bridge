"""
Backward compatibility entry point for local_model_bridge.server
"""
from local_ai_gateway.server import *

if __name__ == "__main__":
    parse_args_and_run()
