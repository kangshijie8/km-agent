# OpenViking Memory Plugin

OpenViking provides high-performance vector memory with GPU acceleration support for Kunming Agent, enabling fast semantic search across large memory datasets.

## Installation

```bash
pip install "kunming-agent[openviking]"
```

Or install the dependencies directly:

```bash
pip install torch transformers faiss-cpu  # or faiss-gpu for GPU support
```

## Configuration

Add to your `~/.kunming/config.yaml`:

```yaml
memory:
  provider: openviking
  config:
    embedding_model: sentence-transformers/all-MiniLM-L6-v2
    device: auto                    # auto, cpu, cuda, mps
    index_type: flat                # flat, ivf, hnsw
    max_memories: 100000
    similarity_threshold: 0.7
    storage_path: ~/.kunming/openviking
    batch_size: 32                  # Embedding batch size
    use_gpu: false                  # Enable GPU acceleration
```

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `embedding_model` | `sentence-transformers/all-MiniLM-L6-v2` | Model for generating embeddings |
| `device` | `auto` | Compute device (auto/cpu/cuda/mps) |
| `index_type` | `flat` | FAISS index type (flat/ivf/hnsw) |
| `max_memories` | `100000` | Maximum memories to store |
| `similarity_threshold` | `0.7` | Minimum cosine similarity for retrieval |
| `storage_path` | `~/.kunming/openviking` | Local storage directory |
| `batch_size` | `32` | Batch size for embedding generation |
| `use_gpu` | `false` | Use GPU for FAISS index |

## How It Works

OpenViking uses FAISS (Facebook AI Similarity Search) for efficient vector retrieval:

1. **Embedding Generation**: Converts text to dense vectors using transformer models
2. **FAISS Indexing**: Stores vectors in optimized index structures
3. **Similarity Search**: Finds nearest neighbors in sub-millisecond time
4. **GPU Acceleration**: Optional CUDA support for large-scale search

## Features

### Multiple Index Types

Choose the right index for your use case:

```yaml
# Exact search, smallest memory
index_type: flat

# Approximate search, faster for large datasets
index_type: ivf
nlist: 100  # Number of Voronoi cells

# Graph-based, best for very large datasets
index_type: hnsw
M: 16       # Connections per node
efConstruction: 200
```

### GPU Acceleration

For large memory stores (100K+ items):

```yaml
memory:
  provider: openviking
  config:
    use_gpu: true
    device: cuda
    index_type: flat  # or ivf for approximate
```

### Dynamic Index Updates

Add and remove memories without rebuilding:

```python
# Add new memories
memory.add(["New fact 1", "New fact 2"])

# Remove by ID
memory.remove(ids=[42, 43])

# Update existing
memory.update(id=42, text="Updated content")
```

## Usage

Configure in your config file:

```yaml
memory:
  provider: openviking
  config:
    embedding_model: sentence-transformers/all-mpnet-base-v2
    index_type: hnsw
    similarity_threshold: 0.75
    max_memories: 50000
```

Use slash commands for manual control:

- `/remember <text>` - Store with automatic embedding
- `/recall <query>` - Semantic search
- `/similar <text>` - Find similar memories
- `/stats` - Show index statistics

## Advanced Configuration

### Custom Embedding Models

Use any sentence-transformers model:

```yaml
memory:
  provider: openviking
  config:
    embedding_model: BAAI/bge-large-en-v1.5
    device: cuda
```

Or local models:

```yaml
memory:
  provider: openviking
  config:
    embedding_model: /path/to/local/model
```

### Hybrid Search

Combine vector similarity with keyword matching:

```yaml
memory:
  provider: openviking
  config:
    hybrid_search: true
    vector_weight: 0.7
    keyword_weight: 0.3
```

### Memory Clustering

Automatically cluster similar memories:

```yaml
memory:
  provider: openviking
  config:
    clustering:
      enabled: true
      n_clusters: 10
      min_cluster_size: 5
```

## Architecture

```
Text Input
    |
    v
+-------------------+
| Embedding Model   |----> Dense Vector (384-1024 dims)
+-------------------+           |
                                v
+-------------------+   +-------------------+
| FAISS Index       |<--| Vector Store      |
| (Flat/IVF/HNSW)   |   +-------------------+
+-------------------+           |
        |                       v
        |               +-------------------+
        +-------------->| Similarity Search |
                        +-------------------+
                                |
                                v
                        +-------------------+
                        | Ranked Results    |
                        +-------------------+
```

## Performance Benchmarks

| Index Type | 10K Items | 100K Items | 1M Items |
|------------|-----------|------------|----------|
| Flat (CPU) | 5ms | 50ms | 500ms |
| Flat (GPU) | 1ms | 5ms | 20ms |
| IVF | 2ms | 5ms | 15ms |
| HNSW | 0.5ms | 1ms | 2ms |

*Query times are approximate and depend on hardware*

## Storage Format

```
~/.kunming/openviking/
├── index.faiss          # FAISS index file
├── metadata.jsonl       # Memory metadata
├── config.json          # Index configuration
└── model/               # Cached embedding model
    └── config.json
    └── pytorch_model.bin
```

## Migration from Other Providers

```bash
# Export from Holographic
km memory export --provider holographic --output holographic.json

# Import to OpenViking
km memory import --provider openviking --source holographic.json
```
