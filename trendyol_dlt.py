import pendulum
import dlt
from dlt.sources.helpers.rest_client import RESTClient
from dlt.sources.helpers.rest_client.paginators import PageNumberPaginator

@dlt.source
def trendyol(
    token=dlt.secrets.value,
    seller_id=dlt.secrets.value
):
    client = RESTClient(
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

    @dlt.resource(
        name="products",
        write_disposition="replace"
    )
    def trendyol_products():
        params = {
            "orderByField": "CreatedDate",
            "orderByDirection": "DESC",
            "size": "50"
        }
        for page in client.paginate(f"integration/product/sellers/{seller_id}/products", params=params):
            yield page

    @dlt.resource(
        name="settlements",
        write_disposition="merge",
        primary_key="id"
    )
    def trendyol_settlements():
        settlement_transaction_types = [
            "Sale", "Return", "Discount", "DiscountCancel", "Coupon", "CouponCancel", 
            "ProvisionPositive", "ProvisionNegative", "SellerRevenuePositive", "SellerRevenueNegative", 
            "CommissionPositive", "CommissionNegative", "SellerRevenuePositiveCancel", 
            "SellerRevenueNegativeCancel", "CommissionPositiveCancel", "CommissionNegativeCancel"
        ]
        
        end_date = pendulum.now(tz="UTC")
        start_date = end_date.subtract(days=30)

        date_ranges = []
        current_start = start_date
        while current_start < end_date:
            segment_end = current_start.add(days=14)
            if segment_end > end_date:
                segment_end = end_date
            
            date_ranges.append((current_start, segment_end))
            current_start = segment_end
        
        for tx_type in settlement_transaction_types:
            for start_dt, end_dt in date_ranges:
                params = {
                    "transactionType": tx_type,
                    "startDate": int(start_dt.timestamp() * 1000),
                    "endDate": int(end_dt.timestamp() * 1000),
                    "size": "500"
                }
        
        for page in client.paginate(f"integration/finance/che/sellers/{seller_id}/settlements", params=params):
            yield page

    @dlt.resource(
        name="otherfinancials",
        write_disposition="merge",
        primary_key="id"
    )
    def trendyol_otherfinancials():
        otherfinancials_transaction_types = [
            "Stoppage", "CashAdvance", "WireTransfer", "IncomingTransfer", 
            "ReturnInvoice", "CommissionAgreementInvoice", "PaymentOrder", 
            "DeductionInvoices", "FinancialItem"
        ]
        
        end_date = pendulum.now(tz="UTC")
        start_date = end_date.subtract(days=30)

        date_ranges = []
        current_start = start_date
        while current_start < end_date:
            segment_end = current_start.add(days=14)
            if segment_end > end_date:
                segment_end = end_date
            
            date_ranges.append((current_start, segment_end))
            current_start = segment_end
        
        for tx_type in otherfinancials_transaction_types:
            for start_dt, end_dt in date_ranges:
                params = {
                    "transactionType": tx_type,
                    "startDate": int(start_dt.timestamp() * 1000),
                    "endDate": int(end_dt.timestamp() * 1000),
                    "size": "500"
                }
        
        for page in client.paginate(f"integration/finance/che/sellers/{seller_id}/otherfinancials", params=params):
            yield page
    @dlt.resource(
        name="packages",
        write_disposition="merge",
    )
    def trendyol_packages(
        last_modified_date=dlt.sources.incremental("lastModifiedDate", initial_value=pendulum.now(tz="Europe/Istanbul").subtract(months=3).timestamp() * 1000)
    ):

        start_date = pendulum.from_timestamp(last_modified_date.start_value / 1000, tz="Europe/Istanbul")
        end_date = pendulum.now(tz="Europe/Istanbul")
        
        current_start = start_date
        date_ranges = []
        while current_start < end_date:
            segment_end = current_start.add(days=14)
            if segment_end > end_date:
                segment_end = end_date
            
            date_ranges.append((current_start, segment_end))
            current_start = segment_end

        for start_dt, end_dt in date_ranges:
            params = {
                "startDate": int(start_dt.timestamp() * 1000), 
                "endDate": int(end_dt.timestamp() * 1000), 
                "orderByField": "lastModifiedDate",
                "orderByDirection": "DESC",
                "size": "50"
            }
            
            for page in client.paginate(f"integration/order/sellers/{seller_id}/orders", params=params):
                yield page

    return trendyol_settlements, trendyol_otherfinancials, trendyol_products, trendyol_packages

pipeline = dlt.pipeline(
    pipeline_name="trendyolAPI",
    destination="postgres",
    dataset_name="raw_trendyol",
    import_schema_path="schemas/import",
    export_schema_path="schemas/export"
)

# Run Pipeline
load_info = pipeline.run(trendyol())

print("\n\n --- Pipeline Başlatma Tarihi ---")
print(load_info.started_at)

print("\n\n --- Pipeline Yükleme Bilgileri ---")
print(load_info)

# print human-friendly trace information
print("\n\n --- Pipeline Trace ---")
print(pipeline.last_trace)
# save trace to destination, sensitive data will be removed
pipeline.run([pipeline.last_trace], table_name="_trace")