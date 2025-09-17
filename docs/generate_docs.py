import os
import json
import logging
import re

OUTPUT_FILE = os.path.join("api_doc", "index.html")
QUERIES_DIR = os.path.join("api_doc", "queries")
TYPES_DIR = os.path.join("api_doc", "types")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


url_pattern = re.compile(r"(https?://[^\s]+)")


def clean_html_parser(text: str) -> str:
    """Replace URLs in text with <a href> links (target=_blank) and newlines with <br>."""
    if not text:
        return ""
    text = url_pattern.sub(r'<a href="\1" target="_blank">\1</a>', text)
    return text.replace("\n", "<br>")


def clean_html(obj):
    if isinstance(obj, str):
        return clean_html_parser(obj)
    elif isinstance(obj, list):
        return [clean_html(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: clean_html(v) for k, v in obj.items()}
    return obj


def load_json_files(folder):
    data = {}
    for fname in sorted(os.listdir(folder)):
        if fname.endswith(".json"):
            fpath = os.path.join(folder, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                try:
                    raw = json.load(f)
                    data[fname.replace(".json", "")] = clean_html(raw)
                except Exception as e:
                    logging.warning(f"Could not parse {fname}: {e}")
    return data


def format_type(t, types):
    if not t:
        return "Unknown"
    base = re.sub(r"[\[\]!]", "", t)
    if base in types:
        kind = types[base].get("kind", "OBJECT")
        kind_map = {
            "OBJECT": "type",
            "INPUT_OBJECT": "input",
            "ENUM": "enum",
            "SCALAR": "scalar",
            "UNION": "union",
            "INTERFACE": "interface",
        }
        prefix = kind_map.get(kind, "type")
        return t.replace(base, f"<a href='#{prefix}-{base}'>{base}</a>")
    return t


def render_args(args, types):
    if not args:
        return "<p>No arguments</p>"
    html = [
        "<table><tr><th>Name</th><th>Type</th><th>Description</th><th>Default</th></tr>"
    ]
    for a in args:
        type_str = format_type(a["type"], types)
        html.append(
            f"<tr><td>{a['name']}</td>"
            f"<td>{type_str}</td>"
            f"<td>{a.get('description','')}</td>"
            f"<td>{a.get('defaultValue','')}</td></tr>"
        )
    html.append("</table>")
    return "\n".join(html)


def generate_section(title, items, types, kind):
    html = [f"<h1 id='{kind}'>{title}</h1>"]
    for name, obj in items.items():
        section_id = f"{kind}-{name}"
        html.append(f"<h2 id='{section_id}'>{name}</h2>")
        if obj.get("description"):
            html.append(f"<p>{obj['description']}</p>")

        if kind == "query":
            html.append("<h3>Arguments</h3>")
            html.append(render_args(obj.get("args", []), types))
            html.append("<h3>Response</h3>")
            html.append(f"<p>{format_type(obj.get('returnType'), types)}</p>")

        elif kind == "type":
            if obj.get("fields"):
                html.append(
                    "<h3>Fields</h3><table><tr><th>Name</th><th>Type</th><th>Description</th></tr>"
                )
                for f in obj["fields"]:
                    type_str = format_type(f["type"], types)
                    field_name = f["name"]
                    if f.get("args"):  # link if args exist
                        link_id = f"{section_id}-{field_name}-args"
                        html.append(
                            f"<tr><td><a href='#{link_id}'>{field_name}</a></td>"
                            f"<td>{type_str}</td>"
                            f"<td>{f.get('description','')}</td></tr>"
                        )
                    else:  # plain text if no args
                        html.append(
                            f"<tr><td>{field_name}</td>"
                            f"<td>{type_str}</td>"
                            f"<td>{f.get('description','')}</td></tr>"
                        )
                html.append("</table>")

                gen_args = False
                for f in obj["fields"]:
                    if f.get("args"):
                        if not gen_args:
                            html.append("<h3>Arguments</h3>")
                            gen_args = True
                        link_id = f"{section_id}-{f['name']}-args"
                        html.append(f"<h4 id='{link_id}'>{f['name']}</h4>")
                        html.append(render_args(f["args"], types))
                
                html.append("<hr/>")

        elif kind == "input":
            if obj.get("inputFields"):
                html.append(
                    "<h3>Input Fields</h3><table><tr><th>Name</th><th>Type</th><th>Description</th><th>Default</th></tr>"
                )
                for f in obj["inputFields"]:
                    type_str = format_type(f["type"], types)
                    html.append(
                        f"<tr><td>{f['name']}</td>"
                        f"<td>{type_str}</td>"
                        f"<td>{f.get('description','')}</td>"
                        f"<td>{f.get('defaultValue','')}</td></tr>"
                    )
                html.append("</table>")

        elif kind == "enum":
            if obj.get("values"):
                html.append(
                    "<h3>Values</h3><table><tr><th>Name</th><th>Description</th></tr>"
                )
                for v in obj["values"]:
                    html.append(
                        f"<tr><td>{v['name']}</td><td>{v.get('description','')}</td></tr>"
                    )
                html.append("</table>")

        elif kind == "scalar":
            html.append(
                "<p>Scalar type — usually built-in (String, Int, Boolean, etc.)</p>"
            )

        elif kind == "union":
            if obj.get("possibleTypes"):
                html.append("<h3>Possible Types</h3><ul>")
                for pt in obj["possibleTypes"]:
                    html.append(f"<li>{format_type(pt['name'], types)}</li>")
                html.append("</ul>")

        elif kind == "interface":
            if obj.get("fields"):
                html.append(
                    "<h3>Fields</h3><table><tr><th>Name</th><th>Type</th><th>Description</th></tr>"
                )
                for f in obj["fields"]:
                    type_str = format_type(f["type"], types)
                    html.append(
                        f"<tr><td>{f['name']}</td>"
                        f"<td>{type_str}</td>"
                        f"<td>{f.get('description','')}</td></tr>"
                    )
                html.append("</table>")

    return "\n".join(html)


def build_html(queries, types):
    grouped = {
        k: {}
        for k in ["OBJECT", "INTERFACE", "ENUM", "SCALAR", "INPUT_OBJECT", "UNION"]
    }
    for name, t in types.items():
        kind = t.get("kind")
        if kind in grouped:
            grouped[kind][name] = t

    def sidebar_section(label, kind, items):
        out = [
            f"<div class='sidebar-section'><div class='section-header' onclick='toggleSection(this)'>{label}</div><ul class='collapsed'>"
        ]
        for n in items:
            out.append(f"<li><a href='#{kind}-{n}'>{n}</a></li>")
        out.append("</ul></div>")
        return "\n".join(out)

    sidebar = ["<div id='sidebar'>"]
    sidebar.append(sidebar_section("Queries", "query", queries))
    sidebar.append(sidebar_section("Types", "type", grouped["OBJECT"]))
    sidebar.append(sidebar_section("Inputs", "input", grouped["INPUT_OBJECT"]))
    sidebar.append(sidebar_section("Enums", "enum", grouped["ENUM"]))
    sidebar.append(sidebar_section("Scalars", "scalar", grouped["SCALAR"]))
    sidebar.append(sidebar_section("Interfaces", "interface", grouped["INTERFACE"]))
    sidebar.append(sidebar_section("Unions", "union", grouped["UNION"]))
    sidebar.append("</div>")

    content = ["<div id='content'>"]
    content.append(generate_section("Queries", queries, types, kind="query"))
    content.append(generate_section("Types", grouped["OBJECT"], types, kind="type"))
    content.append(
        generate_section("Inputs", grouped["INPUT_OBJECT"], types, kind="input")
    )
    content.append(generate_section("Enums", grouped["ENUM"], types, kind="enum"))
    content.append(generate_section("Scalars", grouped["SCALAR"], types, kind="scalar"))
    content.append(
        generate_section("Interfaces", grouped["INTERFACE"], types, kind="interface")
    )
    content.append(generate_section("Unions", grouped["UNION"], types, kind="union"))
    content.append("</div>")

    style = """
    <style>
    body { margin:0; font-family:Arial, sans-serif; }
    #sidebar {
      position:fixed; left:0; top:0; bottom:0;
      width:250px; background:#f8f9fa;
      border-right:1px solid #ddd;
      padding:10px; overflow:auto;
    }
    .sidebar-section { margin-bottom:15px; }
    .section-header { font-weight:bold; cursor:pointer; padding:5px; background:#e9ecef; border:1px solid #ddd; }
    .section-header:hover { background:#dee2e6; }
    .collapsed { display:none; }
    .expanded { display:block; }
    #sidebar ul { list-style:none; padding-left:10px; margin:0; }
    #sidebar li { margin:4px 0; }
    #sidebar a { text-decoration:none; color:#333; }
    #sidebar a.active { font-weight:bold; color:#007bff; }
    #content { margin-left:270px; padding:30px; background:#fff; }
    table { border-collapse:collapse; width:100%; margin-bottom:20px; }
    th, td { border:1px solid #ddd; padding:8px; text-align:left; }
    th { background:#f1f1f1; }
    h1 { margin-top:40px; border-bottom:2px solid #ddd; padding-bottom:5px; }
    h2 { margin-top:30px; color:#2c3e50; }
    h3 { margin-top:20px; }
    </style>
    """

    script = """
    <script>
    function toggleSection(header) {
      const ul = header.nextElementSibling;
      ul.classList.toggle('collapsed');
      ul.classList.toggle('expanded');
    }
    window.addEventListener("scroll", () => {
      let fromTop = window.scrollY + 10;
      document.querySelectorAll("#sidebar a").forEach(link => {
        let section = document.querySelector(link.getAttribute("href"));
        if (section && section.offsetTop <= fromTop && section.offsetTop + section.offsetHeight > fromTop) {
          link.classList.add("active");
        } else {
          link.classList.remove("active");
        }
      });
    });
    </script>
    """

    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>GraphQL Docs</title>{style}</head><body>{''.join(sidebar)}{''.join(content)}{script}</body></html>"


def main():
    logging.info("Loading queries...")
    queries = load_json_files(QUERIES_DIR)
    logging.info(f"Loaded {len(queries)} queries")

    logging.info("Loading types...")
    types = load_json_files(TYPES_DIR)
    logging.info(f"Loaded {len(types)} types")

    logging.info("Building HTML...")
    html = build_html(queries, types)

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    logging.info(f"✅ Documentation generated: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
