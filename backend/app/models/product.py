from dataclasses import dataclass
from typing import Optional

@dataclass
class Product:
    id: str
    name: str
    price: float

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "price": self.price
        }

@dataclass
class CartItem:
    track_id: str
    product_id: str
    quantity: int = 1
    added_at: Optional[str] = None

    def to_dict(self):
        return {
            "track_id": self.track_id,
            "product_id": self.product_id,
            "quantity": self.quantity,
            "added_at": self.added_at
        }
