import os
import json
import requests
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

API_URL = "https://api.meetup.com/gql-ext"
COOKIE_FILE = "meetup.cookie"
OUTPUT_DIR = "api_doc"
QUERY_DIR = os.path.join(OUTPUT_DIR, "queries")
TYPE_DIR = os.path.join(OUTPUT_DIR, "types")

INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    types {
      kind
      name
      description
      fields(includeDeprecated: false) {
        name
        description
        args {
          name
          description
          defaultValue
          type { ...TypeRef }
        }
        type { ...TypeRef }
      }
      inputFields {
        name
        description
        defaultValue
        type { ...TypeRef }
      }
      enumValues(includeDeprecated: true) {
        name
        description
      }
      possibleTypes { name kind }
    }
  }
}

fragment TypeRef on __Type {
  kind
  name
  ofType {
    kind
    name
    ofType {
      kind
      name
      ofType {
        kind
        name
        ofType {
          kind
          name
        }
      }
    }
  }
}
"""


def load_cookies(cookie_file):
    """Load Netscape cookie JSON and return cookie header string."""
    with open(cookie_file, "r") as f:
        cookies = json.load(f)
    return "; ".join([f"{c['name']}={c['value']}" for c in cookies])


def unwrap_type(t):
    """Return a compact string for a GraphQL type (handles nested LIST/NON_NULL)."""
    if t is None:
        return None
    kind = t.get("kind")
    name = t.get("name")
    inner = unwrap_type(t.get("ofType"))

    if kind == "NON_NULL":
        return f"{inner}!"
    if kind == "LIST":
        return f"[{inner}]"
    return name or inner


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def main():
    os.makedirs(QUERY_DIR, exist_ok=True)
    os.makedirs(TYPE_DIR, exist_ok=True)

    # Build headers
    cookie_header = load_cookies(COOKIE_FILE)
    headers = {"Content-Type": "application/json", "Cookie": cookie_header}

    logging.info("Fetching schema from Meetup GraphQL API...")
    resp = requests.post(API_URL, json={"query": INTROSPECTION_QUERY}, headers=headers)
    resp.raise_for_status()
    schema = resp.json()

    # Save full schema
    schema_path = os.path.join(OUTPUT_DIR, "schema.json")
    save_json(schema_path, schema)
    logging.info(f"Full schema saved to {schema_path}")

    schema_data = schema["data"]["__schema"]
    query_type_name = schema_data["queryType"]["name"]

    # Build type index
    types_index = {t["name"]: t for t in schema_data["types"] if t["name"]}

    # Extract queries
    query_type = types_index[query_type_name]
    logging.info(f"Extracting queries from type {query_type_name}...")

    for field in query_type.get("fields", []):
        query_info = {
            "name": field["name"],
            "description": field.get("description"),
            "args": [
                {
                    "name": arg["name"],
                    "description": arg.get("description"),
                    "defaultValue": arg.get("defaultValue"),
                    "type": unwrap_type(arg["type"]),
                }
                for arg in field.get("args", [])
            ],
            "returnType": unwrap_type(field["type"]),
        }

        out_path = os.path.join(QUERY_DIR, f"{field['name']}.json")
        save_json(out_path, query_info)
        logging.info(f"Saved query {field['name']} -> {out_path}")

    # Extract types
    logging.info("Extracting types...")
    skip_prefixes = ("__",)  # skip GraphQL internal types

    for t in schema_data["types"]:
        if not t["name"] or t["name"].startswith(skip_prefixes):
            continue

        type_info = {
            "kind": t["kind"],
            "name": t["name"],
            "description": t.get("description"),
        }

        if t["kind"] in ("OBJECT", "INTERFACE"):
            type_info["fields"] = [
                {
                    "name": f["name"],
                    "description": f.get("description"),
                    "args": [
                        {
                            "name": arg["name"],
                            "description": arg.get("description"),
                            "defaultValue": arg.get("defaultValue"),
                            "type": unwrap_type(arg["type"]),
                        }
                        for arg in f.get("args", [])
                    ],
                    "type": unwrap_type(f["type"]),
                }
                for f in t.get("fields", []) or []
            ]
        elif t["kind"] == "ENUM":
            type_info["values"] = [
                {"name": v["name"], "description": v.get("description")}
                for v in t.get("enumValues", []) or []
            ]
        elif t["kind"] == "SCALAR":
            type_info["scalar"] = True
        elif t["kind"] == "INPUT_OBJECT":
            type_info["inputFields"] = [
                {
                    "name": f["name"],
                    "description": f.get("description"),
                    "defaultValue": f.get("defaultValue"),
                    "type": unwrap_type(f["type"]),
                }
                for f in t.get("inputFields", []) or []
            ]
        elif t["kind"] == "UNION":
            type_info["possibleTypes"] = [
                {"name": pt["name"], "kind": pt["kind"]}
                for pt in t.get("possibleTypes", []) or []
            ]

        out_path = os.path.join(TYPE_DIR, f"{t['name']}.json")
        save_json(out_path, type_info)
        logging.info(f"Saved type {t['name']} -> {out_path}")

    logging.info("✅ Done. Queries and types extracted.")


if __name__ == "__main__":
    main()
