from getpass import getpass

from neo4j import GraphDatabase

uri = "bolt://localhost:7687"
username = "neo4j"

# Пароль вводится вручную и не сохраняется в скрипте.
password = getpass("Пароль Neo4j: ")

query = """
MATCH (student:Student {name: $student_name})
      -[:STUDIES]->(course:Course)
      -[:INCLUDES]->(topic:Topic)
WHERE NOT EXISTS {
    MATCH (student)-[:COMPLETED]->(topic)
}
RETURN student.name AS student,
       course.name AS course,
       topic.name AS remaining_topic
ORDER BY remaining_topic
"""

with GraphDatabase.driver(uri, auth=(username, password)) as driver:
    driver.verify_connectivity()
    print("\nПодключение к Neo4j установлено.")

    with driver.session(database="neo4j") as session:
        records = list(
            session.run(query, student_name="Алексей")
        )

    if not records:
        print("Непройденные темы не найдены.")
    else:
        print("\nТемы, которые студент ещё не прошёл:")
        for record in records:
            print(f"Студент: {record['student']}")
            print(f"Курс: {record['course']}")
            print(f"Тема: {record['remaining_topic']}")
            print()
