from getpass import getpass

from neo4j import GraphDatabase

uri = "bolt://localhost:7687"
password = getpass("Пароль Neo4j: ")

create_query = """
MATCH (course:Course {name: 'Основы машинного обучения'})
MATCH (trees:Topic {name: 'Деревья решений'})

MERGE (basics:Topic {name: 'Основы машинного обучения'})
MERGE (forest:Topic {name: 'Случайный лес'})

MERGE (course)-[:INCLUDES]->(basics)
MERGE (course)-[:INCLUDES]->(forest)

MERGE (basics)-[:PREREQUISITE_FOR]->(trees)
MERGE (trees)-[:PREREQUISITE_FOR]->(forest)

RETURN course.name AS course
"""

nodes_query = """
MATCH (n)
RETURN n.name AS name, labels(n) AS labels
ORDER BY name
"""

relationships_query = """
MATCH (a)-[r]->(b)
RETURN a.name AS source, type(r) AS relation, b.name AS target
ORDER BY source, relation, target
"""

paths_query = """
MATCH path =
    (start:Topic {name: $start_name})
    -[:PREREQUISITE_FOR*1..5]->
    (finish:Topic {name: $finish_name})
RETURN [node IN nodes(path) | node.name] AS topics
"""

connectivity_query = """
MATCH (n)
OPTIONAL MATCH (n)-[r]-()
RETURN n.name AS name, labels(n) AS labels, count(r) AS degree
ORDER BY degree DESC, name
"""

with GraphDatabase.driver(uri, auth=("neo4j", password)) as driver:
    driver.verify_connectivity()
    print("\nПодключение установлено.")

    with driver.session(database="neo4j") as session:
        result = session.run(create_query).single()

        if result is None:
            raise RuntimeError(
                "Курс или тема 'Деревья решений' не найдены. "
                "Проверь, что первоначальный граф создан."
            )

        print("\nГраф расширен для курса:", result["course"])

        print("\nУзлы:")
        for record in session.run(nodes_query):
            print(f"- {record['name']} — {record['labels']}")

        print("\nСвязи:")
        for record in session.run(relationships_query):
            print(
                f"- {record['source']} "
                f"--[{record['relation']}]--> "
                f"{record['target']}"
            )

        print("\nПуть от основ до случайного леса:")
        paths = list(
            session.run(
                paths_query,
                start_name="Основы машинного обучения",
                finish_name="Случайный лес",
            )
        )

        if paths:
            for record in paths:
                print(" → ".join(record["topics"]))
        else:
            print("Путь не найден.")

        print("\nКоличество связей каждого узла:")
        for record in session.run(connectivity_query):
            print(
                f"- {record['name']} "
                f"{record['labels']}: {record['degree']}"
            )

print("\nСоединение закрыто.")
