class OutputBuffer:
    """Collect the stdout of one execution, keeping a bounded size.

    Only the first and the last ``max_chars // 2`` characters are
    stored; the middle is counted but never kept, so the parent's memory
    stays bounded even if the code prints without stopping. ``render()``
    gives the stdout to show to the agent, with a marker telling how
    many characters were removed.

    A new buffer is created for each execution.

    Attributes:
        exec_part1: First characters received (at most half).
        exec_part2: Last characters received, a sliding window of at
            most half.
        length: Total number of characters received, kept or not.
    """
    def __init__(self, max_chars: int = 7000) -> None:
        self.exec_part1: str = ""
        self.exec_part2: str = ""
        self.length = 0
        self.max_output_char = max_chars
        self.half_output_char = self.max_output_char // 2

    def render(self) -> str:
        """Join the kept beginning and end of the stdout.

        If more characters were printed than self.max_output_char, a marker
        giving the number of characters removed is put between the two
        parts.

        Returns:
            The stdout to give to the agent, possibly truncated.
        """
        nb_truncate = self.length - len(self.exec_part1) - len(self.exec_part2)
        if nb_truncate > 0:
            msg: str = (
                f"[Truncated]: {nb_truncate} characters on a"
                f" total of {self.length}."
            )
            return f"{self.exec_part1}...\n{msg}\n...{self.exec_part2}"
        return self.exec_part1 + self.exec_part2

    def add(self, text: str) -> None:
        """Add a piece of stdout to the buffer.

        The piece first fills the beginning; once the beginning is full,
        the rest goes to the end, which keeps only its last characters.

        Args:
            text: Text just written by the executed code.
        """
        if self.length > self.half_output_char:
            self._add_part_two(text)
            self.length += len(text)
            return
        remain_space: int = self.half_output_char - len(self.exec_part1)

        self.length += len(text)
        if remain_space > len(text):
            self.exec_part1 += text
        else:
            self.exec_part1 += text[:remain_space]
            self._add_part_two(text[remain_space:])

    def _add_part_two(self, text: str) -> None:
        """Keep only the last self.half_output_char characters of text.

        Called after each addition to the end of the stdout, so that it
        never grows beyond the limit (sliding window).

        Args:
            text: End of the stdout with the text just printed added.
        """
        self.exec_part2 += text
        if len(self.exec_part2) > self.half_output_char:
            self.exec_part2 = self.exec_part2[-self.half_output_char:]
