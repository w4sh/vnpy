"""
Pytest configuration and shared fixtures for vnpy tests.
"""

import sys
import pytest
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def project_root_dir() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def test_data_dir(project_root_dir: Path) -> Path:
    """Get the test data directory."""
    test_data = project_root_dir / "tests" / "data"
    test_data.mkdir(exist_ok=True)
    return test_data
