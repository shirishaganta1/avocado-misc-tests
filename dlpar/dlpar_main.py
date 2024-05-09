#!/usr/bin/env python
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: 2022 IBM
# Author: Kalpana Shetty <kalshett@in.ibm.com>
# Author(Modified): Samir A Mulani <samir@linux.vnet.ibm.com>

import os
import random

from avocado import Test
from avocado.utils import process
from avocado.utils import wait
from dlpar_api.api import DedicatedCpu, CpuUnit, Memory
list_payload = ["cfg_cpu_per_proc", "hmc_manageSystem", "hmc_user",
                "hmc_passwd", "target_lpar_hostname", "target_partition",
                "target_user", "target_passwd", "ded_quantity_to_test",
                "sleep_time", "iterations", "vir_quantity_to_test",
                "cpu_quantity_to_test", "mem_quantity_to_test",
                "mem_linux_machine"]


IS_POWER_VM = 'pSeries' in open('/proc/cpuinfo', 'r').read()
dlpar_type_flag = ""


class DlparTests(Test):

    """
    Dlpar CPU/MEMORY  tests - ADD/REMOVE/MOVE
    """

    def run_cmd(self, test_cmd, dlpar_type_flag=""):
        os.chmod(test_cmd, 0o755)
        if dlpar_type_flag != "":
            test_cmd = test_cmd + " " + dlpar_type_flag
        result = process.run(test_cmd, shell=True)
        errors = 0
        warns = 0
        for line in result.stdout.decode().splitlines():
            if 'FAILED' in line:
                self.log.info(line)
                errors += 1
            elif 'WARNING' in line:
                self.log.info(line)
                warns += 1

        if errors == 0 and warns > 0:
            self.warn('number of warnings is %s', warns)

        elif errors > 0:
            self.log.warn('number of warnings is %s', warns)
            self.fail("number of errors is %s" % errors)

    @staticmethod
    def get_mcp_component(component):
        '''
        probes IBM.MCP class for mentioned component and returns it.
        '''
        for line in process.system_output('lsrsrc IBM.MCP %s' % component,
                                          ignore_status=True, shell=True,
                                          sudo=True).decode("utf-8") \
                                                    .splitlines():
            if component in line:
                return line.split()[-1].strip('{}\"')
        return ''

    @staticmethod
    def get_partition_name(component):
        '''
        get partition name from lparstat -i
        '''
        for line in process.system_output('lparstat -i', ignore_status=True,
                                          shell=True,
                                          sudo=True).decode("utf-8") \
                                                    .splitlines():
            if component in line:
                a = line.split(':')[-1].strip()
                print(a)
                return a
        return ''

    @staticmethod
    def data_payload_backup(payload_data):
        '''
        taking the back of cpu_payload and mem_payload list
        in order to use them for test_cpu_remove, test_cpu_mix and
        test_mem_remove
        '''
        get_cwd = os.getcwd()
        file_path = 'dlpar_main.py.data/config.txt'
        payload_path = os.path.join(get_cwd, file_path)
        with open(payload_path, 'a') as file:
            # Write configuration data to the file
            file.write(str(payload_data))
            file.write('\n')

    @staticmethod
    def data_payload_extract(payload_path):
        '''
        we are extracting a payload data of cpu and
        memory which we stored in a config file when
        executing test_cpu_add() and test_mem_add()
        '''
        with open(payload_path, 'r') as file:
            # Read all lines from the file
            lines = file.readlines()
        return lines

    @staticmethod
    def cpu_payload_data(max_value, curr_proc, step=1):
        index_list = []
        current_sum = curr_proc
        index = 0

        while True:
            # Calculate the next index value to add
            next_index_value = index

            # Check if adding the next index value exceeds the max_value
            if current_sum + next_index_value > max_value:
                break  # If exceeding, stop adding more index values

            # Add the next index value to the list
            index_list.append(next_index_value)
            current_sum += next_index_value
            index += step  # Increment index by the specified step

        return [value for value in index_list if value != 0]

    @staticmethod
    def mix_payload_data(values):
        '''
        to get random values rather than using the same list which is generated
        through cpu_payload_data for performing mix operations
        '''
        # Calculate the sum of the given list
        total_sum = sum(values)
        random_values = []
        remaining_sum = total_sum

        while remaining_sum > 0:
            # Generate a random value between 1 and the remaining sum
            value = random.randint(1, remaining_sum)
            # Add the value to the list of random values
            random_values.append(value)
            # Update the remaining sum
            remaining_sum -= value

        return random_values

    @staticmethod
    def mem_payload_data(curr_mem, lmb, max_value=0):
        result_list = []
        index_value = lmb
        current_sum = 0
        if max_value == 0:
            # Calculate 80% of curr_mem
            max_value = curr_mem * 0.8
            # Ensure max_value is divisible by lmb
            max_value += lmb - (max_value % lmb)
            current_sum = 0
        else:
            current_sum = curr_mem

        while current_sum + index_value <= max_value:
            result_list.append(int(index_value))
            current_sum += index_value

            # Calculate the remaining capacity to reach max_value
            remaining_capacity = max_value - current_sum

            # Adjust the next index_value based on remaining capacity
            if remaining_capacity <= 0:
                break
            elif remaining_capacity < index_value:
                index_value = remaining_capacity
            else:
                index_value = min(index_value * 2, remaining_capacity)

        return result_list

    def setUp(self):
        self.list_data = []
        self.lpar_mode = self.params.get('lp_mode', default='dedicated')
        for i in list_payload:
            self.data = self.params.get(i, default='')
            self.list_data.append(self.data)

        # Get HMC IP
        self.hmc_ip = wait.wait_for(
            lambda: self.get_mcp_component("HMCIPAddr"), timeout=30)

        # Primary lpar details
        self.pri_partition = self.get_partition_name("Partition Name")
        self.pri_name = self.get_partition_name("Node Name")
        pri_data = {"src_partition": self.pri_partition,
                    "src_name": self.pri_name,
                    "hmc_name": self.hmc_ip}
        self.res = {list_payload[i]: self.list_data[i]
                    for i in range(len(list_payload))}
        self.res = dict(list(pri_data.items()) + list(self.res.items()))
        self.log.info("Calling Config file creation method--!!")
        self.sorted_payload = dict(sorted(self.res.items()))
        self.iterations = self.sorted_payload.get('iterations')

    def test_cpu_add(self):
        if self.lpar_mode == 'dedicated':
            Ded_obj = DedicatedCpu(self.sorted_payload,
                                   log='dedicated_cpu.log')
            max_procs = Ded_obj.get_max_proc()
            self.log.info(max_procs)
            curr_proc = Ded_obj.get_curr_proc()
            self.log.info(curr_proc)
            if max_procs > 20:
                self.cpu_payload = self.cpu_payload_data(
                    max_procs, curr_proc, step=2)
            else:
                self.cpu_payload = self.cpu_payload_data(max_procs, curr_proc)
            self.data_payload_backup(self.cpu_payload)
            self.log.info("====list of cpu's to be added====",
                          self.cpu_payload)
            for cpu in self.cpu_payload:
                rvalue = Ded_obj.add_ded_cpu(cpu)
                if rvalue == 1:
                    self.fail("CPU add Command failed \
                               please check the logs")
                self.log.info("=====> %s cpu got added====>\n " % cpu)
        elif self.lpar_mode == 'shared':
            Sha_obj = CpuUnit(self.sorted_payload, log='cpu_unit.log')
            for i in range(self.iterations):
                rvalue = Sha_obj.add_proc()
                if rvalue == 1:
                    self.fail("Proc add Command failed please check the logs")

    def test_cpu_move(self):
        if self.lpar_mode == 'dedicated':
            Ded_obj = DedicatedCpu(self.sorted_payload,
                                   log='dedicated_cpu.log')
            if Ded_obj.value:
                self.cancel("Failed to connect secondary machine canceling \
                        the move operation")
            for i in range(self.iterations):
                rvalue = Ded_obj.move_ded_cpu()
                if rvalue == 1:
                    self.fail("CPU move Command failed please check the logs")
        elif self.lpar_mode == 'shared':
            Sha_obj = CpuUnit(self.sorted_payload, log='cpu_unit.log')
            if Sha_obj.value == 1:
                self.cancel("Failed to connect secondary machine \
                        canceling the move operation")
            for i in range(self.iterations):
                rvalue = Sha_obj.move_proc()
                if rvalue == 1:
                    self.fail("Proc move Command failed please check the logs")

    def test_cpu_rm(self):
        if self.lpar_mode == 'dedicated':
            Ded_obj = DedicatedCpu(self.sorted_payload,
                                   log='dedicated_cpu.log')
            # We need to read the file in terms of list
            get_cwd = os.getcwd()
            file_path = 'dlpar_main.py.data/config.txt'
            payload_path = os.path.join(get_cwd, file_path)
            loaded_payload_data = self.data_payload_extract(payload_path)
            cpupayload = eval(str(loaded_payload_data[0]))
            self.log.info("list of cpu's to be removed:", cpupayload)
            for cpu in cpupayload:
                rvalue = Ded_obj.rem_ded_cpu(cpu)
                if rvalue == 1:
                    self.fail("CPU remove Command failed please \
                              check the logs")
                self.log.info("====>%s cpus got removed====>\n " % cpu)

        elif self.lpar_mode == 'shared':
            Sha_obj = CpuUnit(self.sorted_payload, log='cpu_unit.log')
            for i in range(self.iterations):
                rvalue = Sha_obj.remove_proc()
                if rvalue == 1:
                    self.fail("Proc remove Command failed please \
                            check the logs")

    def test_mix_cpu(self):
        if self.lpar_mode == 'dedicated':
            Ded_obj = DedicatedCpu(self.sorted_payload,
                                   log='dedicated_cpu.log')
            get_cwd = os.getcwd()
            file_path = 'dlpar_main.py.data/config.txt'
            payload_path = os.path.join(get_cwd, file_path)
            loaded_payload_data = self.data_payload_extract(payload_path)
            cpu_payload = eval(str(loaded_payload_data[0]))
            cpu_mix = self.mix_payload_data(cpu_payload)
            sum_of_allcpu = sum(cpu_mix)
            cpu_mix.append(sum_of_allcpu)
            self.log.info("list of cpu's:", cpu_mix)
            for cpu in cpu_mix:
                rvalue = Ded_obj.add_ded_cpu(cpu)
                if rvalue == 1:
                    self.fail("CPU add Command failed \
                              please check the logs")
                self.log.info("====>%s cpus got added====>\n " % cpu)
                rvalue = Ded_obj.rem_ded_cpu(cpu)
                if rvalue == 1:
                    self.fail("CPU remove Command failed \
                              please check the logs")
                self.log.info("====>%s cpus got removed==+=>\n " % cpu)

    def test_mem_add(self):
        Mem_obj = Memory(self.sorted_payload, log='memory.log')
        max_mem = Mem_obj.get_max_mem()
        curr_mem = Mem_obj.get_curr_mem()
        lmb_value = Mem_obj.get_lmb_size()
        self.mem_payload = self.mem_payload_data(curr_mem, lmb_value, max_mem)
        self.data_payload_backup(self.mem_payload)
        self.log.info("====list of memory to be added====", self.mem_payload)
        for mem in self.mem_payload:
            rvalue = Mem_obj.mem_add(mem)
            if rvalue == 1:
                self.fail("%s Memory add Command failed please \
                               check the logs" % mem)
            self.log.info("====> %s memory got added====>\n " % mem)

    def test_mem_rem(self):
        Mem_obj = Memory(self.sorted_payload, log='memory.log')
        curr_mem = Mem_obj.get_curr_mem()
        lmb_value = Mem_obj.get_lmb_size()
        self.mem_remove = self.mem_payload_data(curr_mem, lmb_value)
        self.data_payload_backup(self.mem_remove)
        self.log.info("====list of memory remove values====", self.mem_remove)
        self.log.info("Sum of memory remove values:", sum(self.mem_remove))
        for mem in self.mem_remove:
            rvalue = Mem_obj.mem_rem(mem)
            if rvalue == 1:
                self.fail("Memory remove Command failed \
                          please check the logs")
            self.log.info("====> %s memory got removed====>\n " % mem)

    def test_mem_mix(self):
        Mem_obj = Memory(self.sorted_payload, log='memory.log')
        get_cwd = os.getcwd()
        file_path = 'dlpar_main.py.data/config.txt'
        payload_path = os.path.join(get_cwd, file_path)
        loaded_payload_data = self.data_payload_extract(payload_path)
        mem_add_list = eval(str(loaded_payload_data[1]))
        self.log.info("memory add list values:", mem_add_list)
        lmb = Mem_obj.get_lmb_size()
        mem_rem_list = []
        for i in mem_add_list:
            i = int(i * 0.8)
            # Ensure max_value is divisible by lmb
            i += lmb - (i % lmb)
            mem_rem_list.append(i)
        self.log.info("memory remove list values:", mem_rem_list)
        for i in range(len(mem_add_list)):
            rvalue = Mem_obj.mem_add(mem_add_list[i])
            if rvalue == 1:
                self.fail("MEM add Command failed \
                          please check the logs")
            self.log.info("====>%s memory got added====>\n " % mem_add_list[i])
            rvalue = Mem_obj.mem_rem(mem_rem_list[i])
            if rvalue == 1:
                self.fail("MEM remove Command failed \
                          please check the logs")
            self.log.info("==>%s memory got removed==>\n " % mem_rem_list[i])

    def test_mem_mov(self):
        Mem_obj = Memory(self.sorted_payload, log='memory.log')
        if Mem_obj.value == 1:
            self.cancel("Failed to connect secondary machine canceling \
                    the move operation")
        rvalue_move = Mem_obj.mem_move()
        if rvalue_move == 1:
            self.fail("Memory move Command failed please check the logs")
