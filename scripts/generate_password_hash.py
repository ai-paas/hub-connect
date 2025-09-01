#!/usr/bin/env python3
"""
Password hash generation utility

Usage:
    python scripts/generate_password_hash.py [password]
    
Example:
    python scripts/generate_password_hash.py admin123
"""

import sys
import os
import logging
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.auth_service import get_password_hash

# Script-specific logger configuration
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def main():
    if len(sys.argv) != 2:
        logger.error("Usage: python generate_password_hash.py <password>")
        logger.error("Example: python generate_password_hash.py admin123")
        sys.exit(1)
    
    password = sys.argv[1]
    hash_value = get_password_hash(password)
    
    logger.info("Password has been entered.")
    logger.info(f"Hash value: {hash_value}")
    logger.info("")
    logger.info("Set this hash value in the .env file's ADMIN_PASSWORD_HASH:")
    logger.info(f"ADMIN_PASSWORD_HASH={hash_value}")

if __name__ == "__main__":
    main()
