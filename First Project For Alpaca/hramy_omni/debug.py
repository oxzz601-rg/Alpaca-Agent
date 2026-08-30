#!/usr/bin/env python3
"""Debug script to check what's happening."""

import sys
import os

# Write to file first to ensure file I/O works
with open('debug_output.txt', 'w') as f:
    f.write("Starting debug script\n")
    f.write(f"Python: {sys.version}\n")
    f.write(f"CWD: {os.getcwd()}\n")
    f.write(f"sys.path[0]: {sys.path[0]}\n")
    
    try:
        f.write("\nAttempting to import trading.option_chain...\n")
        from trading.option_chain import OptionChainResolver
        f.write("✓ Success\n")
    except Exception as e:
        f.write(f"✗ Failed: {e}\n")
        f.write(f"  Type: {type(e).__name__}\n")
        import traceback
        f.write(traceback.format_exc())
    
    try:
        f.write("\nAttempting to import trading.risk...\n")
        from trading.risk import OptionRiskGate
        f.write("✓ Success\n")
    except Exception as e:
        f.write(f"✗ Failed: {e}\n")
        import traceback
        f.write(traceback.format_exc())
    
    try:
        f.write("\nAttempting to import trading.agent_loop...\n")
        from trading.agent_loop import AutonomousAgentLoop
        f.write("✓ Success\n")
    except Exception as e:
        f.write(f"✗ Failed: {e}\n")
        import traceback
        f.write(traceback.format_exc())
    
    f.write("\nDebug script complete\n")

print("Script finished, check debug_output.txt")
