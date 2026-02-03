import torch
from transformers import AutoTokenizer, AutoModel
from typing import List
import logging

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        logger.info(f"Loading embedding model: {model_name}")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name)
        self.model.eval()
        logger.info("Embedding model loaded successfully")

    def generate_single(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        return self.generate_batch([text])[0]

    def generate_batch(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        all_embeddings = []

        # Filter out empty texts
        valid_texts = []
        valid_indices = []
        for i, text in enumerate(texts):
            if text and text.strip():
                valid_texts.append(text.strip())
                valid_indices.append(i)

        if not valid_texts:
            return [None] * len(texts)

        # Process in batches
        for i in range(0, len(valid_texts), batch_size):
            batch_texts = valid_texts[i:i + batch_size]

            encoded = self.tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors='pt'
            )

            with torch.no_grad():
                outputs = self.model(**encoded)

            embeddings = self._mean_pooling(outputs, encoded['attention_mask'])
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)

            all_embeddings.extend(embeddings.tolist())

        # Map back to original indices (None for empty texts)
        result = [None] * len(texts)
        for idx, embedding in zip(valid_indices, all_embeddings):
            result[idx] = embedding

        return result

    def _mean_pooling(self, model_output, attention_mask):
        """Apply mean pooling to get sentence embeddings."""
        token_embeddings = model_output[0]
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(
            input_mask_expanded.sum(1), min=1e-9
        )
