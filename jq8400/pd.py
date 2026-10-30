##
## This file is part of the libsigrokdecode project.
##

import sigrokdecode as srd

CMD_DICT = {
    0x00: '0', 0x01: '1', 0x02: '2', 0x03: '3', 0x04: '4',
    0x05: '5', 0x06: '6', 0x07: '7', 0x08: '8', 0x09: '9',
    0x0A: 'Clear/Reset',
    0x0B: 'Track Select OK',
    0x0C: 'Set Volume OK',
    0x0D: 'Set EQ',
    0x0E: 'Set Loop Mode',
    0x11: 'Play',
    0x12: 'Pause',
    0x13: 'Stop',
    0x14: 'Previous',
    0x15: 'Next'
}

class Decoder(srd.Decoder):
    api_version = 3
    id = 'jq8400'
    name = 'jq8400'
    longname = 'JQ8400 1-Wire'
    desc = 'JQ8400 1-wire voice protocol'
    license = 'gplv2+'
    inputs = ['logic']
    outputs = []
    tags = ['Timing / measurement']  # 必须使用 sigrok 官方已注册的合法分类名称
    channels = (
        {'id': 'sda', 'name': 'SDA', 'desc': 'Data'},
    )
    optional_channels = ()
    options = ()
    annotations = (
        ('bit', 'Bit'),
        ('byte', 'Byte'),
        ('cmd', 'Command'),
    )
    annotation_rows = (
        ('bits', 'Bits', (0,)),
        ('bytes', 'Bytes', (1,)),
        ('cmds', 'Commands', (2,)),
    )

    def __init__(self):
        self.reset()

    def reset(self):
        self.samplerate = None
        self.state = 'IDLE'
        self.edge_fall = 0
        self.edge_rise = 0
        self.bit_count = 0
        self.current_byte = 0
        self.byte_start_samplenum = 0

    def start(self):
        self.out_ann = self.register(srd.OUTPUT_ANN)

    def metadata(self, key, value):
        if key == srd.SRD_CONF_SAMPLERATE:
            self.samplerate = value

    def us_to_samples(self, us):
        return int((us * self.samplerate) / 1000000)

    def decode(self):
        while True:
            # 等待 SDA 电平边沿翻转
            (sda,) = self.wait({0: 'e'})

            if not self.samplerate:
                continue

            lead_min = self.us_to_samples(2000)    # 引导码低电平 > 2ms
            lead_max = self.us_to_samples(10000)   # 引导码低电平 < 10ms
            threshold_us = self.us_to_samples(400) # 区分 0/1 的高电平脉宽门限 (400us)

            if sda == 0:  # 下降沿
                self.edge_fall = self.samplenum

                if self.state == 'DATA':
                    high_width = self.edge_fall - self.edge_rise
                    bit_val = 1 if high_width > threshold_us else 0

                    # 输出 Bit
                    self.put(self.edge_rise, self.edge_fall, self.out_ann,
                             [0, [str(bit_val)]])

                    self.current_byte |= (bit_val << self.bit_count)
                    self.bit_count += 1

                    if self.bit_count == 8:
                        cmd_name = CMD_DICT.get(self.current_byte, 'Unknown')
                        hex_str = '0x%02X' % self.current_byte

                        # 输出 Byte
                        self.put(self.byte_start_samplenum, self.edge_fall, self.out_ann,
                                 [1, [hex_str]])

                        # 输出 Command 文本
                        self.put(self.byte_start_samplenum, self.edge_fall, self.out_ann,
                                 [2, ['%s (%s)' % (cmd_name, hex_str), cmd_name]])

                        self.state = 'IDLE'

            elif sda == 1:  # 上升沿
                self.edge_rise = self.samplenum
                low_width = self.edge_rise - self.edge_fall

                if self.state == 'IDLE':
                    if lead_min <= low_width <= lead_max:
                        self.state = 'DATA'
                        self.bit_count = 0
                        self.current_byte = 0
                        self.byte_start_samplenum = self.edge_rise