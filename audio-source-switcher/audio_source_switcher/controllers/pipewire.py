import subprocess

from PyQt6.QtCore import QThread, pyqtSignal


class PipeWireController:
    """Handles interaction with pw-link for managing PipeWire graph."""

    @staticmethod
    def run_command(args: list[str]) -> str | None:
        try:
            result = subprocess.run(args, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    def get_links(self) -> list[str]:
        """Returns list of lines from pw-link -l"""
        output = self.run_command(['pw-link', '-l'])
        if not output:
            return []
        return output.split('\n')

    def link(self, port_out: str, port_in: str):
        self.run_command(['pw-link', port_out, port_in])

    def unlink(self, port_out: str, port_in: str):
        self.run_command(['pw-link', '-d', port_out, port_in])

    def get_jamesdsp_outputs(self) -> list[str]:
        """Finds the output ports for JamesDSP."""
        output_ports = []
        raw_out = self.run_command(['pw-link', '-o'])
        if raw_out:
            for line in raw_out.split('\n'):
                if "jdsp_" in line and "JamesDsp" in line and ":output_" in line:
                    output_ports.append(line.strip())
        return output_ports

    def get_sink_playback_ports(self, sink_name: str) -> list[str]:
        """Finds the playback ports for a given sink name."""
        input_ports = []
        raw_in = self.run_command(['pw-link', '-i'])
        if raw_in:
            for line in raw_in.split('\n'):
                if sink_name in line and ":playback_" in line:
                    input_ports.append(line.strip())
        return input_ports

    def find_linked_sink(self, jdsp_output_port: str) -> str | None:
        """Given a JamesDSP output port, find the sink it's linked to.

        Parses pw-link -l output to find the target playback port and extracts the sink name.
        Returns the sink name or None if not linked.
        """
        links = self.get_links()
        capture_next = False

        for line in links:
            sline = line.strip()
            if sline == jdsp_output_port:
                capture_next = True
            elif capture_next and line.startswith("  |->"):
                raw_target = line.replace("  |->", "").strip()
                if ":playback_" in raw_target:
                    return raw_target.split(":playback_")[0]
            elif capture_next and not line.startswith("  "):
                capture_next = False

        return None

    def get_jamesdsp_target(self) -> str | None:
        """Returns the name of the sink that JamesDSP is currently routed to.
        Returns None if floating or not found.
        """
        jdsp_outs = self.get_jamesdsp_outputs()
        if not jdsp_outs:
            return None
        return self.find_linked_sink(jdsp_outs[0])

    def relink_jamesdsp(self, target_sink_name: str) -> bool:
        """Disconnects JamesDSP from current HW and connects to target_sink_name."""
        jdsp_outs = self.get_jamesdsp_outputs()
        if not jdsp_outs:
            print("DEBUG: JamesDSP outputs not found (relink failed).")
            return False

        target_ins = self.get_sink_playback_ports(target_sink_name)
        if not target_ins:
            print(f"DEBUG: Target inputs for '{target_sink_name}' not found via pw-link.")
            return False

        # 1. DISCONNECT EXISTING LINKS FIRST
        links = self.get_links()
        for out_port in jdsp_outs:
            capture = False
            for line in links:
                sline = line.strip()
                if sline == out_port:
                    capture = True
                elif capture and line.startswith("  |->"):
                    target = line.replace("  |->", "").strip()
                    if ":playback_" in target:
                        self.unlink(out_port, target)
                elif capture and not line.startswith("  "):
                    capture = False

        # 2. CONNECT NEW LINKS (sort to ensure FL->FL, FR->FR)
        jdsp_outs.sort()
        target_ins.sort()

        count = min(len(jdsp_outs), len(target_ins))
        for i in range(count):
            self.link(jdsp_outs[i], target_ins[i])

        return True


class VolumeMonitorThread(QThread):
    """Monitors 'pactl subscribe' for sink changes.
    When 'jamesdsp_sink' changes volume, it signals the main thread to sync.
    """

    volume_changed_signal = pyqtSignal()

    def run(self):
        process = subprocess.Popen(
            ['pactl', 'subscribe'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        while True:
            line = process.stdout.readline()
            if not line:
                break
            if "Event 'change' on sink" in line:
                self.volume_changed_signal.emit()
