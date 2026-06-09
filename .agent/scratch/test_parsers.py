import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'd:\HRMS\.agent')

# ─── Test Java Parser ────────────────────────────────────────────
from parsers.java_parser import JavaParser
java_src = '''
package com.hrms.employee;

import java.util.List;

public class EmployeeService {

    private EmployeeRepository repo;

    public EmployeeService(EmployeeRepository repo) {
        this.repo = repo;
    }

    public Employee createEmployee(String name, double salary) {
        return new Employee(name, salary);
    }

    public double calculateSalary(Employee emp, Double deductions) {
        return emp.getSalary() - (deductions != null ? deductions : 0.0);
    }

    public interface Validator {
        boolean validate(Employee emp);
    }

    public enum Status { ACTIVE, INACTIVE }
}
'''
p = JavaParser()
r = p.parse(java_src)
print('=== Java ===')
print(f'  classes:    {[c.name for c in r.classes]}')
print(f'  interfaces: {[i.name for i in r.interfaces]}')
print(f'  enums:      {[e.name for e in r.enums]}')
print(f'  methods:    {[m.name for m in r.methods]}')
print(f'  imports:    {len(r.imports)}')
print(f'  error:      {r.error}')
assert any(c.name == 'EmployeeService' for c in r.classes), 'Missing EmployeeService class'
assert any(m.name == 'createEmployee' for m in r.methods), 'Missing createEmployee method'
assert any(m.name == 'calculateSalary' for m in r.methods), 'Missing calculateSalary method'
print('  OK')

# ─── Test Python Parser ──────────────────────────────────────────
from parsers.python_parser import PythonParser
py_src = '''
from typing import List
import os

class LeaveService:
    def request_leave(self, employee_id: int, days: int) -> bool:
        return True

    def approve_leave(self, request_id: int) -> None:
        pass

def send_notification(msg: str):
    print(msg)
'''
pp = PythonParser()
rp = pp.parse(py_src)
print('\n=== Python ===')
print(f'  classes:   {[c.name for c in rp.classes]}')
print(f'  methods:   {[m.name for m in rp.methods]}')
print(f'  functions: {[f.name for f in rp.functions]}')
print(f'  imports:   {len(rp.imports)}')
print(f'  error:     {rp.error}')
assert any(c.name == 'LeaveService' for c in rp.classes)
assert any(m.name == 'request_leave' for m in rp.methods)
assert any(f.name == 'send_notification' for f in rp.functions)
print('  OK')

# ─── Test JS Parser ──────────────────────────────────────────────
from parsers.js_parser import JavaScriptParser
js_src = '''
import axios from 'axios';

class AttendanceService {
    constructor() {}
    markAttendance(empId) { return true; }
}

function formatDate(date) { return date.toISOString(); }
const getReport = (month) => { return []; };
'''
pj = JavaScriptParser()
rj = pj.parse(js_src)
print('\n=== JavaScript ===')
print(f'  classes:   {[c.name for c in rj.classes]}')
print(f'  methods:   {[m.name for m in rj.methods]}')
print(f'  functions: {[f.name for f in rj.functions]}')
print(f'  imports:   {len(rj.imports)}')
print(f'  error:     {rj.error}')
assert any(c.name == 'AttendanceService' for c in rj.classes)
assert any(f.name == 'getReport' for f in rj.functions)
print('  OK')

# ─── Test TS Parser ──────────────────────────────────────────────
from parsers.ts_parser import TypeScriptParser
ts_src = '''
import { Injectable } from '@angular/core';

interface PayrollEntry {
    employeeId: number;
    amount: number;
    process(): void;
}

enum PayStatus { PENDING, PROCESSED, FAILED }

class PayrollService {
    processPayroll(entry: PayrollEntry): boolean { return true; }
}
'''
pt = TypeScriptParser()
rt = pt.parse(ts_src)
print('\n=== TypeScript ===')
print(f'  classes:    {[c.name for c in rt.classes]}')
print(f'  interfaces: {[i.name for i in rt.interfaces]}')
print(f'  enums:      {[e.name for e in rt.enums]}')
print(f'  methods:    {[m.name for m in rt.methods]}')
print(f'  error:      {rt.error}')
assert any(c.name == 'PayrollService' for c in rt.classes)
assert any(i.name == 'PayrollEntry' for i in rt.interfaces)
assert any(e.name == 'PayStatus' for e in rt.enums)
print('  OK')

print('\nALL PARSER TESTS PASSED')
