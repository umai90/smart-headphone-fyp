import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'module-1', 'deepfake_detection'))
from mode2_online_translation import start_flask_api
start_flask_api()
