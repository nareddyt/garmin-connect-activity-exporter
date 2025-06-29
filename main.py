import sys

from source.config import Config
from source.exporter import Exporter

def main():
    """Main entry point."""
    try:
        config = Config.from_environment()
    except ValueError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)
    
    exporter = Exporter(config)
    exporter.run_scheduled()

if __name__ == '__main__':
    main()
