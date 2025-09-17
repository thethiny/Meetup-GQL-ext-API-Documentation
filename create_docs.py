from docs.generate_docs import main as generate_docs
from docs.generate_schema import main as generate_schema

if __name__ == "__main__":
    generate_schema()
    generate_docs()