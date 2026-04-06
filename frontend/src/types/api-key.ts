/** API Key Siêu dữ liệu (để hiển thị danh sách, không bao gồm khóa đầy đủ). */
export interface ApiKeyInfo {
  id: number;
  name: string;
  key_prefix: string;
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
}

/** Tạo API Key Phản hồi (bao gồm cả khóa đầy đủ, chỉ xuất hiện trong Tạo). */
export interface CreateApiKeyResponse {
  id: number;
  name: string;
  key: string;
  key_prefix: string;
  created_at: string;
  expires_at: string | null;
}
