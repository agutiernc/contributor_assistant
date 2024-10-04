import os
import time
import json
import anthropic
from elasticsearch import Elasticsearch
from sentence_transformers import SentenceTransformer

# doing hybrid search with rrf

ELASTIC_URL = os.getenv("ELASTIC_URL", "http://elasticsearch:9200")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "your-api-key-here")


es_client = Elasticsearch(ELASTIC_URL)
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
model = SentenceTransformer("multi-qa-MiniLM-L6-cos-v1")


# Apply Reciprocal Rank Fusion (RRF) to combine and rerank search results
def compute_rrf(rank, k=60):
    """ Own implementation of the relevance score """
    
    return 1 / (k + rank)

def elastic_search_hybrid_rrf(field, query, vector, k=60, index_name="contributing_h4la"):
    knn_query = {
        "knn": {
            "field": field,
            "query_vector": vector,
            "k": 10,
            "num_candidates": 1000,
            "boost": 0.5,
        },
        "size": 10
    }
    
    keyword_query = {
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["page_content^2", "header_1", "header_2", "header_3", "header_4", "header_5"],
                "type": "best_fields",
                "boost": 0.5,
            }
        },
        "size": 10
    }
    
    # Perform searches
    knn_results = es_client.search(index=index_name, body=knn_query)['hits']['hits']
    keyword_results = es_client.search(index=index_name, body=keyword_query)['hits']['hits']
    
    # Apply RRF
    rrf_scores = {}
    
    for rank, hit in enumerate(knn_results):
        doc_id = hit['_id']
        rrf_scores[doc_id] = compute_rrf(rank + 1, k)
    
    for rank, hit in enumerate(keyword_results):
        doc_id = hit['_id']
        
        if doc_id in rrf_scores:
            rrf_scores[doc_id] += compute_rrf(rank + 1, k)
        else:
            rrf_scores[doc_id] = compute_rrf(rank + 1, k)
    
    # Sort and get top results
    reranked_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    
    final_results = []
    
    for doc_id, score in reranked_docs[:5]:
        doc = es_client.get(index=index_name, id=doc_id)
        
        final_results.append(doc['_source'])


    return final_results


def build_prompt(query, search_results):
    prompt_template = """
    You're an assistant to an open source software engineering project on github. Answer the QUESTION based on
    the CONTEXT from our contributor FAQ database.
    Use only the facts and relevant hyperlinks, if any, from the CONTEXT when answering the QUESTION.

    QUESTION: {question}

    CONTEXT:
    {context}
    """.strip()

    entry_template = """
    page_content: {page_content}
    """.strip()

    context = ""
    
    for doc in search_results:
        context = context + entry_template.format(**doc) + "\n\n"

    prompt = prompt_template.format(question=query, context=context).strip()

    return prompt


def llm(prompt, model_choice):
    start_time = time.time()

    if model_choice.startswith('claude/'):
        model_type = "claude-3-haiku-20240307" if "haiku" in model_choice else "claude-3-5-sonnet-20240620"
        
        response = claude_client.messages.create(
            model= model_type,
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        answer = response.content[0].text

        tokens = {
            'prompt_tokens': response.usage.prompt_tokens,
            'completion_tokens': response.usage.completion_tokens,
            'total_tokens': response.usage.total_tokens
        }
    else:
        raise ValueError(f"Unknown model choice: {model_choice}")
    
    end_time = time.time()
    response_time = end_time - start_time
    
    return answer, tokens, response_time


def evaluate_relevance(question, answer):
    prompt_template = """
    You are an expert evaluator for a Retrieval-Augmented Generation (RAG) system.
    Your task is to analyze the relevance of the generated answer to the given question.
    Based on the relevance of the generated answer, you will classify it
    as "NON_RELEVANT", "PARTLY_RELEVANT", or "RELEVANT".

    Here is the data for evaluation:

    Question: {question}
    Generated Answer: {answer}

    Please analyze the content and context of the generated answer in relation to the question
    and provide your evaluation in parsable JSON without using code blocks:

    {{
      "Relevance": "NON_RELEVANT" | "PARTLY_RELEVANT" | "RELEVANT",
      "Explanation": "[Provide a brief explanation for your evaluation]"
    }}
    """.strip()

    prompt = prompt_template.format(question=question, answer=answer)
    evaluation, tokens, _ = llm(prompt, 'claude/3-haiku')
    
    try:
        json_eval = json.loads(evaluation)

        return json_eval['Relevance'], json_eval['Explanation'], tokens
    except json.JSONDecodeError:
        return "UNKNOWN", "Failed to parse evaluation", tokens


def calculate_claude_pricing(prompt_tokens, completion_tokens, 
                                 price_per_1m_prompt_tokens, 
                                 price_per_1m_completion_tokens):
    """
    Calculate the cost of using Anthropic API based on the number of tokens.
    
    Args:
    - prompt_tokens (int): The number of tokens in the prompt.
    - completion_tokens (int): The number of tokens in the completion.
    - price_per_1m_prompt_tokens (float): Price per 1 million prompt tokens (default = $0.150).
    - price_per_1m_completion_tokens (float): Price per 1 million completion tokens (default = $0.600).

    Returns:
    - total_cost (float): The total cost of the API usage.
    """
    
    # Calculate the cost for prompt tokens
    prompt_cost = (prompt_tokens / 1000000) * price_per_1m_prompt_tokens
    
    # Calculate the cost for completion tokens
    completion_cost = (completion_tokens / 1000000) * price_per_1m_completion_tokens
    
    # Total cost is the sum of both prompt and completion costs
    total_cost = prompt_cost + completion_cost
    
    return total_cost


def calculate_claude_cost(model_choice, tokens):
    claude_cost = 0

    if model_choice == 'claude/3-haiku':
        claude_cost = (tokens['prompt_tokens'] * 0.00025 + tokens['completion_tokens'] * 0.000125) / 1000
    else:
        claude_cost = (tokens['prompt_tokens'] * 0.003 + tokens['completion_tokens'] * 0.015) / 1000

    return claude_cost


def get_answer(query, model_choice):
    vector = model.encode(query)

    search_results = elastic_search_hybrid_rrf('page_content_vector', query, vector)
    prompt = build_prompt(query, search_results)

    answer, tokens, response_time = llm(prompt, model_choice)
    
    relevance, explanation, eval_tokens = evaluate_relevance(query, answer)

    claude_cost = calculate_claude_cost(model_choice, tokens)
 
    return {
        'answer': answer,
        'response_time': response_time,
        'relevance': relevance,
        'relevance_explanation': explanation,
        'model_used': model_choice,
        'prompt_tokens': tokens['prompt_tokens'],
        'completion_tokens': tokens['completion_tokens'],
        'total_tokens': tokens['total_tokens'],
        'eval_prompt_tokens': eval_tokens['prompt_tokens'],
        'eval_completion_tokens': eval_tokens['completion_tokens'],
        'eval_total_tokens': eval_tokens['total_tokens'],
        'claude_cost': claude_cost
    }