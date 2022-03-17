#!/usr/bin/env python3
from setuptools import setup

# skill_id=package_name:SkillClass
PLUGIN_ENTRY_POINT = 'skill-soundcloud.jarbasai=skill_soundcloud:SoundCloudSkill'

setup(
    # this is the package name that goes on pip
    name='skill-soundcloud',
    version='0.0.1',
    description='ovos common play soundcloud skill plugin',
    url='https://github.com/JarbasSkills/skill-soundcloud',
    author='JarbasAi',
    author_email='jarbasai@mailfence.com',
    license='Apache-2.0',
    package_dir={"skill_soundcloud": ""},
    package_data={'skill_soundcloud': ['locale/*', 'ui/*']},
    packages=['skill_soundcloud'],
    include_package_data=True,
    install_requires=["ovos-plugin-manager>=0.0.1a3",
                      "nuvem_de_som",
                      "ovos_workshop>=0.0.5a1"],
    keywords='ovos skill plugin',
    entry_points={'ovos.plugin.skill': PLUGIN_ENTRY_POINT}
)
