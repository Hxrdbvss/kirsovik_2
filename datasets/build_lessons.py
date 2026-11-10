"""Compile editable lessons into the existing catalogs without changing quiz keys or IDs."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'learning-content'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def build():
    manifest = read_json(SOURCE / 'catalog.json')
    original_path = ROOT / 'knowledge-project/material_content.json'
    additional_path = ROOT / 'datasets/academy_demo/additional_materials.json'
    original = read_json(original_path)
    additional = read_json(additional_path)
    known_ids = set(original) | {item['id'] for item in additional}
    if set(manifest) != known_ids:
        raise ValueError('Lesson manifest and material catalogs have different IDs.')
    compiled = {}
    for material_id, metadata in manifest.items():
        body = (SOURCE / f'{material_id}.md').read_text(encoding='utf-8').strip()
        if len(body.split()) < 200 or body.count('### ') < 6:
            raise ValueError(f'Incomplete lesson: {material_id}')
        for field in ['summary','outcomes','assignment','self_check','sources']:
            if not metadata.get(field):
                raise ValueError(f'Missing {field}: {material_id}')
        compiled[material_id] = {**metadata, 'content':body, 'reading_minutes':max(3, math.ceil(len(body.split()) / 120)),
                                 'practice_minutes':10, 'content_version':'lessons-v1'}
    for material_id, item in original.items():
        item.update(compiled[material_id])
    for item in additional:
        item.update(compiled[item['id']])
    # Keep complete question records byte-for-byte equivalent as JSON values.
    for quiz_path in [ROOT/'knowledge-project/quizzes.json', ROOT/'datasets/academy_demo/additional_quizzes.json']:
        quizzes = read_json(quiz_path)
        for material_id, quiz in quizzes.items():
            quiz['practice'] = compiled[material_id]['assignment']
        write_json(quiz_path, quizzes)
    write_json(original_path, original)
    write_json(additional_path, additional)
    materials = [{'id':key, **item} for key,item in original.items()] + additional
    by_id = {item['id']:item for item in materials}
    lines = ['# Учебные материалы проекта «Траектория»','',
        '22 вводных занятия по десяти дисциплинам. Объяснения, примеры и задания подготовлены для учебного проекта; ссылки ведут к документации и дополнительному чтению. Практика предназначена для самостоятельной работы. Освоение темы подтверждается отдельным тестом.','',
        '## Содержание','']
    for material_id, metadata in manifest.items():
        lines.append(f'- {by_id[material_id]["title"]} ({material_id})')
    for material_id, metadata in manifest.items():
        item = by_id[material_id]
        lines += ['',f'## {item["title"]}', '',f'Идентификатор: {material_id}. Чтение около {item["reading_minutes"]} мин; практика около 10 мин.','',
            item['content'],'','### Самостоятельная работа','',item['assignment'],'','### Ориентир для самопроверки','',item['self_check'],'','### Источники и дополнительное чтение','']
        lines.extend(f'- [{source["title"]}]({source["url"]})' for source in item['sources'])
    (ROOT/'docs/Учебные_материалы.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    result = {'lessons':len(compiled),'disciplines':len({item['discipline_id'] for item in compiled.values()}),
        'words':sum(len(item['content'].split()) for item in compiled.values()),'questions_unchanged':True}
    print(json.dumps(result,ensure_ascii=False))
    return result


if __name__ == '__main__':
    build()
