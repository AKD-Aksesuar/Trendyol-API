import time
import threading
import pendulum
import dlt
import logging
from dlt.sources.helpers.rest_client import RESTClient
from dlt.sources.helpers.rest_client.paginators import PageNumberPaginator

# === Logger Setup ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trendyol_pipeline")

# === Rate Limited REST Client with Retry and Logging ===
class RateLimitedRESTClient(RESTClient):
    _lock = threading.Lock()
    _last_request_time = 0
    _min_interval = 60 / 2000  # 2000 requests per minute

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)  # Retry strategy

    def _rate_limit(self):
        with self._lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last_request_time = time.time()

    def get(self, *args, **kwargs):
        self._rate_limit()
        try:
            return super().get(*args, **kwargs)
        except Exception as e:
            logger.error(f"GET request failed: {e}")
            raise

    def paginate(self, *args, **kwargs):
        for page in super().paginate(*args, **kwargs):
            self._rate_limit()
            yield page

# === DLT Source Definition ===
@dlt.source
def trendyol(token=dlt.secrets.value, seller_id=dlt.secrets.value):
    client = RateLimitedRESTClient(
        base_url="https://apigw.trendyol.com",
        headers={
            "Authorization": f"Basic {token}",
            "User-Agent": f"{seller_id} - SelfIntegration",
            "Accept": "application/json"
        },
        paginator=PageNumberPaginator(
            total_path="totalPages",
            page_param="page",
            base_page=0
        )
    )

    @dlt.resource(name="products", write_disposition="replace")
    def trendyol_products():
        logger.info("Fetching products...")
        params = {
            "orderByField": "CreatedDate",
            "orderByDirection": "DESC",
            "size": "50"
        }
        try:
            for page in client.paginate(f"integration/product/sellers/{seller_id}/products", params=params):
                yield from page
        except Exception as e:
            logger.error(f"[products] Error: {e}")

    @dlt.resource(name="settlements", write_disposition="merge", primary_key="id")
    def trendyol_settlements():
        logger.info("Fetching settlements...")
        types = [
            "Sale", "Return", "Discount", "DiscountCancel", "Coupon", "CouponCancel",
            "ProvisionPositive", "ProvisionNegative", "SellerRevenuePositive", "SellerRevenueNegative",
            "CommissionPositive", "CommissionNegative", "SellerRevenuePositiveCancel",
            "SellerRevenueNegativeCancel", "CommissionPositiveCancel", "CommissionNegativeCancel"
        ]
        end_date = pendulum.now("UTC")
        start_date = end_date.subtract(days=14)

        date_ranges = []
        current = start_date
        while current < end_date:
            next_range = min(current.add(days=14), end_date)
            date_ranges.append((current, next_range))
            current = next_range

        try:
            for tx_type in types:
                for start_dt, end_dt in date_ranges:
                    params = {
                        "transactionType": tx_type,
                        "startDate": int(start_dt.timestamp() * 1000),
                        "endDate": int(end_dt.timestamp() * 1000),
                        "size": "500"
                    }
                    for page in client.paginate(f"integration/finance/che/sellers/{seller_id}/settlements", params=params):
                        yield from page
        except Exception as e:
            logger.error(f"[settlements] Error: {e}")

    @dlt.resource(name="otherfinancials", write_disposition="merge", primary_key="id")
    def trendyol_otherfinancials():
        logger.info("Fetching other financials...")
        types = [
            "Stoppage", "CashAdvance", "WireTransfer", "IncomingTransfer",
            "ReturnInvoice", "CommissionAgreementInvoice", "PaymentOrder",
            "DeductionInvoices", "FinancialItem"
        ]
        end_date = pendulum.now("UTC")
        start_date = end_date.subtract(days=14)

        date_ranges = []
        current = start_date
        while current < end_date:
            next_range = min(current.add(days=14), end_date)
            date_ranges.append((current, next_range))
            current = next_range

        try:
            for tx_type in types:
                for start_dt, end_dt in date_ranges:
                    params = {
                        "transactionType": tx_type,
                        "startDate": int(start_dt.timestamp() * 1000),
                        "endDate": int(end_dt.timestamp() * 1000),
                        "size": "500"
                    }
                    for page in client.paginate(f"integration/finance/che/sellers/{seller_id}/otherfinancials", params=params):
                        yield from page
        except Exception as e:
            logger.error(f"[otherfinancials] Error: {e}")

    @dlt.resource(name="packages", write_disposition="merge")
    def trendyol_packages(
        last_modified_date=dlt.sources.incremental("lastModifiedDate", initial_value=pendulum.now("Europe/Istanbul").subtract(months=3).timestamp() * 1000)
    ):
        logger.info("Fetching packages...")
        start_date = pendulum.from_timestamp(last_modified_date.start_value / 1000, tz="Europe/Istanbul")
        end_date = pendulum.now("Europe/Istanbul")

        date_ranges = []
        current = start_date
        while current < end_date:
            next_range = min(current.add(days=14), end_date)
            date_ranges.append((current, next_range))
            current = next_range

        try:
            for start_dt, end_dt in date_ranges:
                params = {
                    "startDate": int(start_dt.timestamp() * 1000),
                    "endDate": int(end_dt.timestamp() * 1000),
                    "orderByField": "lastModifiedDate",
                    "orderByDirection": "DESC",
                    "size": "50"
                }
                for page in client.paginate(f"integration/order/sellers/{seller_id}/orders", params=params):
                    for record in page:
                        yield last_modified_date.update(record)
        except Exception as e:
            logger.error(f"[packages] Error: {e}")

    return trendyol_products, trendyol_settlements, trendyol_otherfinancials, trendyol_packages

# === DLT Pipeline Setup and Execution ===
pipeline = dlt.pipeline(
    pipeline_name="trendyolAPI",
    destination="postgres",
    dataset_name="raw_trendyol",
    import_schema_path="schemas/import",
    export_schema_path="schemas/export"
)

if __name__ == "__main__":
    logger.info("Pipeline başlatılıyor...")
    load_info = pipeline.run(trendyol())

    logger.info("Pipeline tamamlandı.")
    logger.info(f"Başlama Zamanı: {load_info.started_at}")
    logger.info(f"Yüklenen Kayıtlar: {load_info}")
    
    logger.info("--- Pipeline Trace ---")
    print(pipeline.last_trace)
    pipeline.run([pipeline.last_trace], table_name="_trace")
