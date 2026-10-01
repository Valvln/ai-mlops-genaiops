# Distributed training

**Status: documented, not built.** Distributed training was cut on 2026-08-15
for cost: it needs several nodes, usually GPU nodes, and this subscription's
GPU quota was never requested. Nothing below was run.

Every behavioural claim comes from the Microsoft Learn pages under *Sources*,
read on **2026-10-01**. Exam objective: *Manage distributed training for large
and deep learning models*.

---

## 1. Two kinds of parallelism

| | Data parallelism | Model parallelism |
| --- | --- | --- |
| What is split | the **data**, one partition per node | the **model**, one part per node |
| Each node holds | the **whole model** | a part of the model |
| Each node sees | its own subset of data | the same data |
| Synchronisation | parameters or gradients after each batch | shared parameters, once per forward or backward step |
| Constraint | the model must **fit on one node** | harder to implement |
| When | most cases; "sufficient for most use cases" | the model doesn't fit on one node |

Learn: "More than 90% of the time, you should use **distributed data
parallelism**."

---

## 2. PyTorch

- Use **`DistributedDataParallel` (DDP)**, which PyTorch recommends over
  `DataParallel` and over the multiprocessing package.
- Backends: `mpi`, `nccl`, `gloo`. **`nccl` for GPU training.**
- **No launcher needed.** Don't wrap the script in `torch.distributed.launch`.
  Declare the distribution on the job:

```yaml
resources:
  instance_count: 2              # nodes
distribution:
  type: pytorch
  process_count_per_instance: 4  # usually the GPUs per node
```

- **`process_count_per_instance` defaults to 1** process per node. Set it to the
  number of GPUs per node, or the other GPUs sit idle.
- Azure ML sets `MASTER_ADDR`, `MASTER_PORT`, `WORLD_SIZE`, `NODE_RANK` on each
  node, and `RANK`, `LOCAL_RANK` per process. `init_method` defaults to
  `env://`, which reads them.
- `WORLD_SIZE` is the total process count, normally the total number of GPUs.
  `LOCAL_RANK` 0 is where once-per-node work goes, such as data preparation.

### DeepSpeed

Supported as a top-level feature through PyTorch distribution or MPI, with the
DeepSpeed launcher and autotuning. A curated environment bundles DeepSpeed, ONNX
Runtime and PyTorch.

---

## 3. TensorFlow

- Native `tf.distribute.Strategy`: declare `type: tensorflow` with
  `worker_count`. Azure ML sets **`TF_CONFIG`** on each worker.
- Legacy parameter-server strategy (TF 1.x): also set
  `parameter_server_count`.

## 4. MPI

`type: mpi` with `process_count_per_instance` (required). Horovod runs on MPI.

---

## 5. InfiniBand

Linear scaling (one VM 100 s, two VMs 50 s) needs low-latency GPU-to-GPU
links across nodes. **InfiniBand needs RDMA-capable SKUs, usually with `r` in
the name**: `Standard_NC24rs_v3` has it, `Standard_NC24s_v3` doesn't, with the
same cores, RAM and GPUs. On those SKUs the AmlCompute OS image includes the
OFED driver.

---

## 6. Elsewhere

- **AutoML** distributes LightGBM and TCNForecaster (`automl.md` § 6).
- **Sweeps** take a `distribution` and `resources.instance_count` on the trial,
  so each trial can itself be distributed (`hyperparameter-sweep.md`).
- NCv3 was retired on 2025-09-30; clusters on it must be recreated with another
  size.

---

## 7. What this repository measured, and what it did not

**Measured:** nothing distributed. The cluster is CPU, `Standard_DS1_v2`, one
vCPU per node, max 2 nodes. Two adjacent facts from `compute-cost-model.md`:
cost scales with node time, and the only GPU families with quota above zero on
this subscription were NC and NV (§ 2, read 2026-08-11), both retired series.

**Not measured:** any multi-node job, any GPU job, environment variables set by
the platform.

---

## 8. What this note would cost to verify

A two-node CPU job with `type: pytorch`, backend `gloo`, printing the
environment variables on each rank, would show § 2 on the existing cluster for
two activations, about 0.10 €. GPU needs a quota request first.

---

## Sources

- [Distributed training with Azure Machine Learning](https://learn.microsoft.com/en-us/azure/machine-learning/concept-distributed-training): read 2026-10-01 (ms.date 2025-11-24); § 1
- [Distributed GPU training guide (SDK v2)](https://learn.microsoft.com/en-us/azure/machine-learning/how-to-train-distributed-gpu): read 2026-10-01 (ms.date 2026-01-14); §§ 2–5
- [CLI (v2) sweep job YAML schema](https://learn.microsoft.com/en-us/azure/machine-learning/reference-yaml-job-sweep): read 2026-10-01 (ms.date 2024-12-03); distribution types, `process_count_per_instance` for MPI
- [What are compute targets in Azure Machine Learning?](https://learn.microsoft.com/en-us/azure/machine-learning/concept-compute-target): read 2026-10-01 (ms.date 2026-03-31); retired series
- `compute-cost-model.md`: § 7
