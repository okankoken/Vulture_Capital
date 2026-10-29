from datetime import timedelta
import os
import sys
import pendulum
from airflow.sdk import dag, task


@dag(dag_id="vulture_capital_daily",schedule="30 2 * * *",
     start_date=pendulum.datetime(2026,10,28,tz="Europe/Istanbul"),
     catchup=False,max_active_runs=1,is_paused_upon_creation=False,
     tags=["vulture-capital","BIST","NASDAQ-NYSE"],
     default_args={"retries":1,"retry_delay":timedelta(minutes=20)},
     dagrun_timeout=timedelta(hours=20))
def daily():
    @task
    def refresh_symbol_lists():
        sys.path.insert(0,"/opt/vulture")
        os.environ["VULTURE_DATA_DIR"]="/opt/vulture/data"
        from vulture.symbols import refresh_all
        refresh_all()

    @task(execution_timeout=timedelta(hours=18))
    def update_all_markets():
        sys.path.insert(0,"/opt/vulture")
        os.environ["VULTURE_DATA_DIR"]="/opt/vulture/data"
        from vulture.pipeline import run
        run()

    @task(trigger_rule="all_done",retries=2,retry_delay=timedelta(minutes=5))
    def publish_to_streamlit():
        sys.path.insert(0,"/opt/vulture")
        os.environ["VULTURE_DATA_DIR"]="/opt/vulture/data"
        from vulture.publish import publish
        publish()

    refresh_symbol_lists() >> update_all_markets() >> publish_to_streamlit()


daily()
