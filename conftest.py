# pytest must never collect these, even with "pytest ." from this folder:
# test_hashbrown.py asks the REAL Hashbrown AI as soon as it's imported (costs money),
# and web/ has its own tests (python3 -m unittest discover -s web/tests).
collect_ignore = ["test_hashbrown.py", "web"]
