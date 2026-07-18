#!/usr/bin/env python3
"""
Retrieve TRG (trigger) table information from the OTS run-log database.

Extracts config -> custom -> TriggerConfigTable details including:
  - name
  - alias
  - content
  - version
"""

import json
import sys
from daqpy.runlog import RunLog


def get_trigger_config_table(run_number):
    """
    Retrieve TriggerConfigTable info from the trigger subsystem config.
    
    Args:
        run_number: The run number to query
        
    Returns:
        dict with keys: name, alias, content, version
        None if not found or if the data structure is missing
    """
    rl = RunLog()
    
    # Get trigger config for the run
    trigger_config = rl.get_run_config_trigger(run_number)
    
    if trigger_config is None:
        print(f"No trigger config found for run {run_number}")
        return None
    
    print(f"Retrieved trigger config for run {run_number}")
    
    # Extract the config JSONB object
    config = trigger_config.get("config")
    if not config:
        print("Error: No 'config' field in trigger config")
        return None
    
    # Navigate: config -> custom -> TriggerConfigTable
    custom = config.get("custom")
    if not custom:
        print("Error: No 'custom' field in config")
        return None
    
    trg_table = custom.get("TriggerConfigTable")
    if not trg_table:
        print("Error: No 'TriggerConfigTable' found in custom config")
        return None
    
    # Extract the required fields
    result = {
        "name": trg_table.get("name"),
        "alias": trg_table.get("alias"),
        "content": trg_table.get("content"),
        "version": trg_table.get("version"),
    }
    
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python get_trigger_config.py <run_number>")
        print("Example: python get_trigger_config.py 1234")
        sys.exit(1)
    
    try:
        run_num = int(sys.argv[1])
    except ValueError:
        print(f"Error: '{sys.argv[1]}' is not a valid run number")
        sys.exit(1)
    
    result = get_trigger_config_table(run_num)
    
    if result:
        print("\nTriggerConfigTable info:")
        print(json.dumps(result, indent=2))
    else:
        sys.exit(1)
