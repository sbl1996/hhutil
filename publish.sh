rm -rf build
rm -rf dist
rm -rf hhutil.egg-info
python setup.py sdist bdist_wheel
twine upload dist/*