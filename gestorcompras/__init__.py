import importlib, sys
package = importlib.import_module('GestorCompras_.gestorcompras')
sys.modules[__name__] = package
