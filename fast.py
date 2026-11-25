from datetime import datetime, timezone
import random
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import sessionmaker, declarative_base, Session, relationship

DATABASE_URL = "postgresql://order_api_user:StrongPassword123!@localhost/sales_orders_db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()



class UploadBatch(Base):
    __tablename__ = "upload_batches"

    notification_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    tracking_number = Column(String, unique=True, index=True)
    request_type = Column(String, default="DATA_UPLOADS")
    in_date_utc = Column(DateTime(timezone=True))
    status = Column(Integer, default=0)
    stamp_user = Column(String, default="system")
    order_type = Column(String, default="SO")
    number_of_orders = Column(Integer)
    raw_payload = Column(JSON)

    orders = relationship("SalesOrderRecord", back_populates="batch")
    lines = relationship("SalesOrderLineRecord", back_populates="batch")


class SalesOrderRecord(Base):
    __tablename__ = "sales_orders"

    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(Integer, ForeignKey("upload_batches.notification_id"))
    transaction_mode = Column(String)
    order_number = Column(String, index=True)
    order_reference_number = Column(String, index=True)
    order_date = Column(String)
    order_year = Column(String)
    customer_code = Column(String)
    order_version = Column(String)
    type_of_delivery = Column(String)
    transport_mode_code = Column(String)
    origin_country = Column(String)
    origin_city = Column(String)
    destination_country = Column(String)
    destination_city = Column(String)
    full_header_json = Column(JSON)

    batch = relationship("UploadBatch", back_populates="orders")


class SalesOrderLineRecord(Base):
    __tablename__ = "sales_order_lines"

    id = Column(Integer, primary_key=True, index=True)
    notification_id = Column(Integer, ForeignKey("upload_batches.notification_id"))
    order_reference_number = Column(String, index=True)
    order_number = Column(String, index=True)
    so_sequence = Column(String)
    sku = Column(String, index=True)
    item_name = Column(String)
    hs_code = Column(String)
    item_list_price = Column(String)
    packages = Column(String)
    received_packages = Column(String)
    origin_site_name = Column(String)
    destination_site_name = Column(String)
    full_line_json = Column(JSON)

    batch = relationship("UploadBatch", back_populates="lines")


Base.metadata.create_all(bind=engine)


# --- Pydantic Schemas ---
class FlexibleObject(BaseModel):
    model_config = ConfigDict(extra="allow")


class SalesOrderItem(FlexibleObject):
    transactionMode: Optional[str] = ""
    orderNumber: str
    orderDate: Optional[str] = ""
    orderYear: Optional[str] = ""
    customerCode: Optional[str] = ""
    orderVersion: Optional[str] = ""
    orderReferenceNumber: str
    typeOfDelivery: Optional[str] = ""
    transportModeCode: Optional[str] = ""
    originCountry: Optional[str] = ""
    originCity: Optional[str] = ""
    destinationCountry: Optional[str] = ""
    destinationCity: Optional[str] = ""


class SalesOrderLineItem(FlexibleObject):
    orderReferenceNumber: str
    orderNumber: str
    soSequence: Optional[str] = ""
    sku: Optional[str] = ""
    itemName: Optional[str] = ""
    hsCode: Optional[str] = ""
    itemListPrice: Optional[str] = ""
    packages: Optional[str] = ""
    receivedPackages: Optional[str] = ""
    originSiteName: Optional[str] = ""
    destinationSiteName: Optional[str] = ""


class UploadInfo(BaseModel):
    salesOrder: List[SalesOrderItem]
    salesOrderlines: List[SalesOrderLineItem]


class OrderUploadRequest(BaseModel):
    uploadInfo: UploadInfo


# --- FastAPI App ---
app = FastAPI(title="Sales Order Upload API")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.post("/v1/order-upload/SO")
def upload_sales_orders(payload: OrderUploadRequest, db: Session = Depends(get_db)):
    now_utc = datetime.now(timezone.utc)
    tracking_num = f"TN{random.randint(10000000, 99999999)}"
    orders_list = payload.uploadInfo.salesOrder
    lines_list = payload.uploadInfo.salesOrderlines
    order_refs = [o.orderReferenceNumber for o in orders_list]

    batch = UploadBatch(
        tracking_number=tracking_num,
        request_type="DATA_UPLOADS",
        in_date_utc=now_utc,
        status=0,
        stamp_user="system",
        order_type="SO",
        number_of_orders=len(orders_list),
        raw_payload=payload.model_dump(),
    )
    db.add(batch)
    db.flush()  # Generates batch.notification_id

    for order in orders_list:
        db.add(
            SalesOrderRecord(
                notification_id=batch.notification_id,
                transaction_mode=order.transactionMode,
                order_number=order.orderNumber,
                order_reference_number=order.orderReferenceNumber,
                order_date=order.orderDate,
                order_year=order.orderYear,
                customer_code=order.customerCode,
                order_version=order.orderVersion,
                type_of_delivery=order.typeOfDelivery,
                transport_mode_code=order.transportModeCode,
                origin_country=order.originCountry,
                origin_city=order.originCity,
                destination_country=order.destinationCountry,
                destination_city=order.destinationCity,
                full_header_json=order.model_dump(),
            )
        )

    for line in lines_list:
        db.add(
            SalesOrderLineRecord(
                notification_id=batch.notification_id,
                order_reference_number=line.orderReferenceNumber,
                order_number=line.orderNumber,
                so_sequence=line.soSequence,
                sku=line.sku,
                item_name=line.itemName,
                hs_code=line.hsCode,
                item_list_price=line.itemListPrice,
                packages=line.packages,
                received_packages=line.receivedPackages,
                origin_site_name=line.originSiteName,
                destination_site_name=line.destinationSiteName,
                full_line_json=line.model_dump(),
            )
        )

    db.commit()

    return {
        "status": "ACCEPTED",
        "message": "Processing order(s) upload.",
        "data": {
            "notificationId": batch.notification_id,
            "trackingNumber": [tracking_num],
            "requestType": "DATA_UPLOADS",
            "inDateUtc": now_utc.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "status": 0,
            "stampUser": "system",
            "summary": {
                "orderType": "SO",
                "orderRefNumber": order_refs,
                "numberOfOrders": len(orders_list),
            },
            "deleted": 0,
            "notificationDesc": "Uploading Orders",
        },
    }


@app.get("/v1/order-upload/SO/{tracking_number}")
def get_upload_by_tracking(tracking_number: str, db: Session = Depends(get_db)):
    batch = (
        db.query(UploadBatch)
        .filter(UploadBatch.tracking_number == tracking_number)
        .first()
    )
    if not batch:
        return {"status": "NOT_FOUND", "message": "Tracking number not found."}
    return {
        "notificationId": batch.notification_id,
        "trackingNumber": batch.tracking_number,
        "inDateUtc": batch.in_date_utc,
        "numberOfOrders": batch.number_of_orders,
        "payload": batch.raw_payload,
    }
