"""
main.py — AI Radar
===================
Entry point.

Usage:
    python main.py              # run pipeline once right now
    python main.py --deploy     # register 07:00 daily schedule with Prefect
    python main.py --validate   # check config and API keys, then exit
"""

import sys
import logging
from config import settings, validate_on_startup

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

if __name__ == "__main__":
    validate_on_startup()

    if "--validate" in sys.argv:
        print("Config OK. Exiting.")
        sys.exit(0)

    from pipeline.flow import epoch_pipeline, create_scheduled_deployment

    if "--deploy" in sys.argv:
        create_scheduled_deployment()
    else:
        epoch_pipeline()
