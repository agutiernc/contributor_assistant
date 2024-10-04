import os
import requests
import pandas as pd
from sentence_transformers import SentenceTransformer
from elasticsearch import Elasticsearch
from tqdm.auto import tqdm
from dotenv import load_dotenv
from db import init_db

load_dotenv()

ELASTIC_URL = os.getenv("ELASTIC_URL_LOCAL")
MODEL_NAME = os.getenv("MODEL_NAME")
INDEX_NAME = os.getenv("INDEX_NAME")

BASE_URL = "https://github.com/agutiernc/contributor_assistant/blob/main"


def fetch_documents():
    print("Fetching documents...")

    relative_url = "/data/documents.json"
    docs_url = f"{BASE_URL}/{relative_url}?raw=1"
    docs_response = requests.get(docs_url)
    documents = docs_response.json()

    print(f"Fetched {len(documents)} documents")

    return documents


def fetch_ground_truth():
    print("Fetching ground truth data...")

    relative_url = "/data/ground-truth-retrieval.csv"
    ground_truth_url = f"{BASE_URL}/{relative_url}?raw=1"

    df_ground_truth = pd.read_csv(ground_truth_url)
    ground_truth = df_ground_truth.to_dict(orient="records")

    print(f"Fetched {len(ground_truth)} ground truth records")

    return ground_truth


def load_model():
    print(f"Loading model: {MODEL_NAME}")

    return SentenceTransformer(MODEL_NAME)


def setup_elasticsearch():
    print("Setting up Elasticsearch...")

    es_client = Elasticsearch(ELASTIC_URL)

    index_settings = {
      "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0
      },
      "mappings": {
        "dynamic": True,
        "properties": {
          "id": { "type": "keyword" },
          "page_content": { "type": "text" },
          "header_1": { "type": "text" },
          "header_2": { "type": "text" },
          "header_3": { "type": "text" },
          "header_4": { "type": "text"},
          "header_5": { "type": "text"},
          "page_content_vector": {
            "type": "dense_vector",
            "dims": 384,
            "index": True,
            "similarity": "cosine"
          }
        }
      }
    }

    es_client.indices.delete(index=INDEX_NAME, ignore_unavailable=True)
    es_client.indices.create(index=INDEX_NAME, body=index_settings)

    print(f"Elasticsearch index '{INDEX_NAME}' created")

    return es_client


def index_documents(es_client, documents, model):
    print("Indexing documents...")

    for doc in tqdm(documents):
      # extract content from doc
      content = doc.get('page_content')
 
      # encode content
      doc['page_content_vector'] = model.encode(content)

      es_client.index(index=INDEX_NAME, document=doc)
      
    print(f"Indexed {len(documents)} documents")


def main():
    # if you just want to init the db or didn't want to re-index
    print("Starting the indexing process...")

    documents = fetch_documents()
    ground_truth = fetch_ground_truth()
    model = load_model()
    es_client = setup_elasticsearch()
    
    index_documents(es_client, documents, model)

    print("Initializing database...")

    init_db()

    print("Indexing process completed successfully!")


if __name__ == "__main__":
    main()