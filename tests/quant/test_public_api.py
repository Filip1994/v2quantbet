from h2h.quant import DixonColesFitError, DixonColesModel, dixon_coles_tau
from h2h.quant.dixon_coles import DixonColesFitError as ModuleFitError
from h2h.quant.dixon_coles import DixonColesModel as ModuleModel
from h2h.quant.dixon_coles import dixon_coles_tau as module_tau


def test_public_quant_exports_are_canonical() -> None:
    assert DixonColesModel is ModuleModel
    assert DixonColesFitError is ModuleFitError
    assert dixon_coles_tau is module_tau


def test_public_tau_function_is_callable() -> None:
    assert dixon_coles_tau(0, 0, 1.4, 1.1, -0.05) == 1.077
