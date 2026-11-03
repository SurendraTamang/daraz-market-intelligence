export interface Product {
  name: string;
  category: string;
  price: number;
  originalPrice: number | null;
  discount: number | null;
  sold: number;
  revenue: number;
  rating: number;
  reviews: number;
  brand: string;
  generic: boolean;
  seller: string;
  location: string;
  score: number;
  levers: { demand: number; afford: number; quality: number; competition: number; velocity: number; generic: number };
}

export interface Category {
  category: string;
  revenue: number;
  units: number;
  products: number;
  sellers: number;
  avgPrice: number;
  genericShare: number;
}

export interface Data {
  meta: { run?: string; products: number; units: number; revenue: number; sellers: number; categories: number };
  categories: Category[];
  products: Product[];
}
