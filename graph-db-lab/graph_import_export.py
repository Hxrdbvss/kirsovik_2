import csv
import json
from getpass import getpass
from pathlib import Path

from neo4j import GraphDatabase

csv_path = Path("learning_materials.csv")

if not csv_path.is_file():
    raise FileNotFoundError(f"Файл {csv_path} не найден.")

with csv_path.open(encoding="utf-8", newline="") as file:
    materials = list(csv.DictReader(file))

password = getpass("Пароль Neo4j: ")

import_query = """
UNWIND $materials AS material
MATCH (topic:Topic {name: material.topic})
MERGE (resource:Material {id: material.id})
SET resource.title = material.title,
    resource.level = material.level
MERGE (topic)-[:HAS_MATERIAL]->(resource)
RETURN count(resource) AS imported
"""

missing_query = """
UNWIND $materials AS material
OPTIONAL MATCH (topic:Topic {name: material.topic})
WITH material, count(topic) AS matches
WHERE matches = 0
RETURN material.id AS id, material.topic AS topic
"""

nodes_query = """
MATCH (n)
RETURN labels(n) AS labels, properties(n) AS properties
ORDER BY coalesce(n.name, n.title, n.id)
"""

relationships_query = """
MATCH (a)-[r]->(b)
RETURN coalesce(a.name, a.title, a.id) AS source,
       type(r) AS relationship,
       coalesce(b.name, b.title, b.id) AS target
ORDER BY source, relationship, target
"""

with GraphDatabase.driver(
    "bolt://localhost:7687",
    auth=("neo4j", password),
) as driver:
    driver.verify_connectivity()

    with driver.session(database="neo4j") as session:
        missing = list(session.run(missing_query, materials=materials))

        if missing:
            print("\nНе найдены темы для следующих материалов:")
            for record in missing:
                print(f"- {record['id']}: {record['topic']}")
            raise SystemExit(
                "Импорт остановлен. Проверь названия тем в CSV."
            )

        result = session.run(import_query, materials=materials).single()
        print(f"\nОбработано материалов: {result['imported']}")

        nodes = [record.data() for record in session.run(nodes_query)]
        relationships = [
            record.data() for record in session.run(relationships_query)
        ]

with open("graph_nodes_export.csv", "w", encoding="utf-8", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(["labels", "properties"])
    for node in nodes:
        writer.writerow([
            ", ".join(node["labels"]),
            json.dumps(node["properties"], ensure_ascii=False),
        ])

with open(
    "graph_relationships_export.csv",
    "w",
    encoding="utf-8",
    newline="",
) as file:
    writer = csv.DictWriter(
        file,
        fieldnames=["source", "relationship", "target"],
    )
    writer.writeheader()
    writer.writerows(relationships)

print(f"Экспортировано узлов: {len(nodes)}")
print(f"Экспортировано связей: {len(relationships)}")
print("\nСозданы файлы:")
print("- graph_nodes_export.csv")
print("- graph_relationships_export.csv")
