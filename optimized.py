import placer


def main() -> None:
    args = placer.parse_args()
    args.mode = "random"
    args.candidate_count = 8
    placer.run_terminal(args)


if __name__ == "__main__":
    main()
