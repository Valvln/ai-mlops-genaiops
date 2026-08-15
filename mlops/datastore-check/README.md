# Datastore check

The verification job for [feature 004](../../specs/004-datastore-compute-cluster/spec.md).
It trains nothing. It answers one question: **can a node of the compute cluster
read a known file through a datastore that carries no credential?**

## Why a checksum and not an exit code

The feature specification names the failure mode this guards against: a job that
starts, logs, and exits zero would satisfy a naive check while proving nothing
about data access. So the evidence is a digest that cannot be produced without
having read the bytes, compared against a value recorded **before the job
existed**.

## The known file

`sample.csv` — five rows of meaningless numbers. Its only property that matters
is that its identity was recorded first.

| Property | Value |
| --- | --- |
| Bytes | **164** |
| sha256 | **`498429272d6251d8da130431385c3acfa0be0f47cb172e24370dc350183e2148`** |
| Rows, excluding header | **5** |

Recorded 2026-08-15, on the author's machine, before the datastore existed:

```bash
wc -c < sample.csv
shasum -a 256 sample.csv
tail -n +2 sample.csv | wc -l
```

**The job passes when its logged values equal all three of these.** Not when it
reaches `Completed`.

## What proves what

| File | Its job |
| --- | --- |
| `sample.csv` | The known quantity. Changing it invalidates the table above — recompute and update it in the same commit. |
| `check_datastore.py` | Reads the mounted input once and derives every figure from that single read. Standard library only. |
| `job.yml` | Addresses the input **through the datastore** (`azureml://datastores/…`), not through a storage URL. Pointing it at a storage URL would make the job pass while testing nothing about the datastore. |

Two choices in `job.yml` are declared rather than defaulted, and both for the
same reason — a default that has not been read is not a decision:

- **`identity: managed`** selects the cluster's own system-assigned identity.
  There are three candidate identities for a datastore read (the submitting
  user, the workspace, the compute), and leaving this blank means not knowing
  which one performed it.
- **`type: uri_file`** rather than `uri_folder`, so a wrong path fails at mount
  time rather than inside the script.

## Running it

```bash
export PATH="/usr/local/bin:$PATH"
az ml job create -g rg-ai300-test01 -w <workspace> -f job.yml --stream
```

Read the values back out of the log:

```bash
az ml job stream -g rg-ai300-test01 -w <workspace> -n <job-name> | grep DATASTORE-CHECK
```

Cost: roughly **0.005 €** — one `Standard_DS1_v2` node for a few minutes, plus
the 120-second idle tail before the cluster scales back to zero.

## Before you conclude anything from a green run

The run is only meaningful if the author's own identity **cannot** read that
blob. Owner is a management-plane role and confers no blob data access, so the
check is:

```bash
az storage blob download --account-name <account> --container-name training-data \
  --name sample.csv --file /tmp/nope.csv --auth-mode login   # expected to FAIL
```

If that command succeeds, the job's success no longer distinguishes the cluster
identity from the author's, and the evidence is gone. See
[quickstart.md § 3](../../specs/004-datastore-compute-cluster/quickstart.md).
