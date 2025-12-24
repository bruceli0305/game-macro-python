from core.models.base import BaseFile
from core.models.skill import SkillsFile, Skill
from core.models.point import PointsFile, Point

print(BaseFile.from_dict({}).to_dict())
print(SkillsFile.from_dict({"skills":[{"id":"1","name":"A","pixel":{"tolerance":12}}]}).to_dict())
print(PointsFile.from_dict({"points":[{"id":"2","name":"P","x":10,"y":20}]}).to_dict())