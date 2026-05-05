import sys
sys.path.insert(0, 'src')

print('Step 1: sys.path set')

try:
    from agent_loop import AgentLoop
    print('Step 2: AgentLoop imported successfully')
    print(f'_generate_session_id method exists: {hasattr(AgentLoop, "_generate_session_id")}')
    
    # Check method location
    import agent_loop
    print(f'agent_loop module: {agent_loop}')
    print(f'agent_loop.AgentLoop: {agent_loop.AgentLoop}')
    
    # Test the method
    agent = AgentLoop.__new__(AgentLoop)
    result = agent._generate_session_id()
    print(f'_generate_session_id result: {result}')
except Exception as e:
    print(f'Import failed: {e}')
    import traceback
    traceback.print_exc()