import os

from tests import clock

# The developer's .env sets PUBLIC_URL, and with it the notices link their games and the emails have a base: the suite
# runs as CI does, with none. A test that needs one patches `config.PUBLIC_URL` itself (load_dotenv never overrides a variable
# that is already set, even to an empty one).
os.environ["PUBLIC_URL"] = ""

clock.install_on_first_run()
