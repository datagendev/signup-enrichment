"""
Simple random number generator
"""
import random


def generate_random_number(min_value: int = 1, max_value: int = 100) -> int:
    """
    Generate a random integer between min_value and max_value (inclusive)
    
    Args:
        min_value: Minimum value (default: 1)
        max_value: Maximum value (default: 100)
        
    Returns:
        Random integer
    """
    return random.randint(min_value, max_value)


if __name__ == "__main__":
    # Example usage
    number = generate_random_number()
    print(f"Random number: {number}")

