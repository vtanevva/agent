#!/usr/bin/env python3

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app.tools.calendar_manager import list_calendar_events
    from app.agent_core.tool_registry import call
    
    print("Testing calendar tool directly...")
    
    # Test the tool directly
    result = list_calendar_events("vanesa.taneva@gmail.com")
    print(f"Direct tool result: {result}")
    
    # Test through the registry
    result2 = call("list_calendar_events", user_id="vanesa.taneva@gmail.com")
    print(f"Registry tool result: {result2}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
