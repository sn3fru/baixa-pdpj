"""
Devedor360 v2 - Pipeline Completo
Executa Step 1 → Step 2 → Step 3 em sequencia.
Ponto de entrada unico para CLI e frontend.

Uso CLI:
    python pipeline.py                         # roda tudo
    python pipeline.py --step s1               # so coleta
    python pipeline.py --step s2               # so organizacao
    python pipeline.py --step s3               # so visao devedor
    python pipeline.py --step s1 s2            # coleta + organizacao
    python pipeline.py --processos "123-45..." # busca processos especificos

Uso frontend (Flask/FastAPI/Streamlit):
    from pipeline import Pipeline
    p = Pipeline(Config(tokens=[...], download_detalhes=True))
    resultado = p.executar(steps=["s1", "s2", "s3"], callback=my_cb)
"""

import argparse
import sys
import time
from datetime import datetime

from config import Config


class Pipeline:
    """
    Orquestrador do pipeline completo.

    Parametros:
        config: Config injetavel (None = from_env)
        progress_callback: callable(step, event, data) para frontend
    """

    def __init__(self, config: Config = None, progress_callback=None):
        self.cfg = config or Config.from_env()
        self.cb = progress_callback
        self.resultados = {}

    def executar(self, steps: list = None) -> dict:
        """
        Executa os steps indicados em sequencia.
        steps: ["s1", "s2", "s3"]  (None = todos)
        Retorna dict com resultados de cada step.
        """
        if steps is None:
            steps = ["s1", "s2", "s3"]

        inicio = time.time()
        self._emit("pipeline_inicio", {"steps": steps})

        if "s1" in steps:
            self.resultados["s1"] = self._run_s1()

        if "s2" in steps:
            self.resultados["s2"] = self._run_s2()

        if "s3" in steps:
            self.resultados["s3"] = self._run_s3()

        elapsed = time.time() - inicio
        self.resultados["elapsed"] = elapsed
        self._emit("pipeline_fim", {"elapsed": elapsed})
        return self.resultados

    def executar_por_processos(self, numeros: list) -> dict:
        """Busca detalhes de processos especificos (atalho)."""
        from s1_coleta_unificada import executar_coleta_processos
        return executar_coleta_processos(numeros, self.cfg)

    # ---- Steps privados ------------------------------------------------

    def _run_s1(self) -> dict:
        print("\n" + "=" * 60)
        print("  STEP 1 - COLETA UNIFICADA")
        print("=" * 60)
        from s1_coleta_unificada import executar_coleta

        def cb_s1(evt, data):
            self._emit("s1", evt, data)

        return executar_coleta(self.cfg, progress_callback=cb_s1 if self.cb else None)

    def _run_s2(self):
        print("\n" + "=" * 60)
        print("  STEP 2 - ORGANIZACAO DE PROCESSOS")
        print("=" * 60)
        from s2_organiza_processos import executar_organizacao, consolidar_paginas

        def cb_s2(evt, data):
            self._emit("s2", evt, data)

        if self.cfg.download_detalhes:
            df = executar_organizacao(self.cfg,
                                      progress_callback=cb_s2 if self.cb else None)
        else:
            df = consolidar_paginas(self.cfg)

        return {"total_processos": len(df), "colunas": list(df.columns)}

    def _run_s3(self):
        print("\n" + "=" * 60)
        print("  STEP 3 - VISAO DEVEDOR")
        print("=" * 60)
        from s3_visao_devedor import executar_visao_devedor

        def cb_s3(evt, data):
            self._emit("s3", evt, data)

        # Se s2 retornou DataFrame, passa direto
        df_s2 = self.resultados.get("s2", {}).get("_df")
        df = executar_visao_devedor(self.cfg, df_processos=df_s2,
                                     progress_callback=cb_s3 if self.cb else None)
        return {"total_entidades": len(df)}

    def _emit(self, step_or_evt, evt_or_data=None, data=None):
        if self.cb:
            try:
                if data is not None:
                    self.cb(step_or_evt, evt_or_data, data)
                else:
                    self.cb("pipeline", step_or_evt, evt_or_data)
            except Exception:
                pass


# ============================================================================
# API de conveniencia
# ============================================================================

def executar_pipeline(config: Config = None, steps: list = None,
                       progress_callback=None) -> dict:
    """Funcao unica para rodar o pipeline completo."""
    return Pipeline(config, progress_callback).executar(steps)


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Devedor360 v2 - Pipeline")
    parser.add_argument("--step", nargs="*", default=None,
                        choices=["s1", "s2", "s3"],
                        help="Steps a executar (default: todos)")
    parser.add_argument("--processos", nargs="*",
                        help="Lista de numeros de processo para buscar")
    parser.add_argument("--debug", action="store_true",
                        help="Habilita modo debug")
    args = parser.parse_args()

    cfg = Config.from_env()
    if args.debug:
        cfg.debug = True

    cfg.imprimir()
    erros = cfg.validar()
    if erros:
        print("\n[ERRO] Configuracao invalida:")
        for e in erros:
            print(f"  - {e}")
        sys.exit(1)

    inicio = time.time()

    if args.processos:
        print(f"\nBuscando {len(args.processos)} processo(s) especifico(s)...")
        res = Pipeline(cfg).executar_por_processos(args.processos)
        print(f"Resultados: {len(res)} detalhes baixados")
    else:
        steps = args.step or ["s1", "s2", "s3"]
        res = executar_pipeline(cfg, steps=steps)

    elapsed = time.time() - inicio
    m, s = divmod(int(elapsed), 60)
    print(f"\n{'=' * 60}")
    print(f"  PIPELINE FINALIZADO em {m:02d}:{s:02d}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
