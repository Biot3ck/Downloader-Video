import argparse
import json
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--url")
    parser.add_argument("--job-id")
    parser.add_argument("--sleep", type=float, default=0)
    args = parser.parse_args()

    if not args.test:
        if not args.url or not args.job_id:
            print("Missing --url or --job-id", file=sys.stderr)
            return 2

        from real_download_worker_v8 import process_video

        result = process_video(args.url, args.job_id)
        print(json.dumps(result), flush=True)
        return 0

    if args.sleep < 0:
        print("Invalid sleep duration", file=sys.stderr)
        return 2

    time.sleep(args.sleep)

    result = {
        "success": True,
        "mode": "test",
        "message": "Worker completed successfully",
    }

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
