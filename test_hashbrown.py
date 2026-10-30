"""
🥔 Quick check that Hashbrown can reach your Foundry model, without starting the chat.

Run:  python test_hashbrown.py      (in the same folder as server.py)
The key comes from the HASHBROWN_API_KEY environment variable, or else from api_key in
hashbrown_config.json, exactly like the server reads it.
"""
import server

server.hashbrown = server.load_hashbrown()
if server.hashbrown is None:
    print("❌ Hashbrown is off. Set the HASHBROWN_API_KEY environment variable and try again.")
else:
    print("⏳ Asking Hashbrown...")
    try:
        answer = server.call_hashbrown([
            {"role": "system", "content": server.HASHBROWN_PROMPT},
            {"role": "user", "content": "Say hi to the chat in one short sentence."},
        ])
        print("✅ It works! Hashbrown says:", answer)
    except Exception as e:
        print("❌ Didn't work:", e)
