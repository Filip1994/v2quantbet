def test_corner_modeler_fits_without_retired_labs_or_redundant_offline_audits(monkeypatch):
    from h2h import cornerlab_modeler_entrypoint as module
    calls = []
    class Repository:
        def __init__(self,url): calls.append(('database',url))
        def check_database(self): return True
    class Model:
        def __init__(self,repository): pass
        def readiness(self,*,decision_at):
            calls.append(('fit',decision_at))
            return {'reason':'MODEL_READY','artifact_reused':True}
    monkeypatch.setenv('DATABASE_URL','isolated-test')
    monkeypatch.delenv('QUANTBET_QUANTLAB_DATABASE_URL',raising=False)
    monkeypatch.setattr(module,'PostgreSQLQuantLabRepository',Repository)
    monkeypatch.setattr(module,'CornerPressureModelService',Model)
    monkeypatch.setattr(module,'configure_logging',lambda level:None)
    module.main()
    assert [c[0] for c in calls] == ['database','fit']
