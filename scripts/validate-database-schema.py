#!/usr/bin/env python3
"""
Database Schema Validation Script
Validates that Order and Inventory services have properly initialized their database schemas
"""

import asyncio
import asyncpg
import sys
import os
from datetime import datetime
from typing import List, Dict, Any

class DatabaseSchemaValidator:
    def __init__(self):
        self.db_url = "postgresql://user:password@localhost:5432/oxygen_platform"
        self.test_results = []
        
        # Expected tables for each service
        self.expected_tables = {
            "order-service": ["orders", "order_items", "order_status_history"],
            "inventory-service": ["cylinders", "cylinder_stock", "inventory_locations", 
                                "stock_movements", "stock_reservations"]
        }
        
        # Expected columns for critical tables
        self.expected_columns = {
            "orders": ["id", "reference", "hospital_id", "vendor_id", "status", "total_amount"],
            "order_items": ["id", "order_id", "cylinder_size", "quantity", "unit_price"],
            "order_status_history": ["id", "order_id", "status", "notes", "updated_by"],
            "cylinders": ["id", "serial_number", "vendor_id", "cylinder_size", "lifecycle_state"],
            "cylinder_stock": ["id", "inventory_id", "cylinder_size", "total_quantity", 
                             "available_quantity", "reserved_quantity"],
            "inventory_locations": ["id", "vendor_id", "location_name", "address", "latitude", "longitude"],
            "stock_movements": ["id", "inventory_id", "stock_id", "movement_type", "quantity"],
            "stock_reservations": ["id", "inventory_id", "stock_id", "order_id", "quantity", "expires_at"]
        }
    
    def log_test(self, test_name: str, status: str, details: str = ""):
        """Log test result"""
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_icon} {test_name}: {status}")
        if details:
            print(f"   Details: {details}")
    
    async def connect_to_database(self):
        """Test database connectivity"""
        try:
            conn = await asyncpg.connect(self.db_url)
            await conn.close()
            self.log_test("Database Connectivity", "PASS", "Successfully connected to PostgreSQL")
            return True
        except Exception as e:
            self.log_test("Database Connectivity", "FAIL", f"Error: {str(e)}")
            return False
    
    async def get_existing_tables(self) -> List[str]:
        """Get list of existing tables"""
        try:
            conn = await asyncpg.connect(self.db_url)
            query = """
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name
            """
            rows = await conn.fetch(query)
            await conn.close()
            return [row['table_name'] for row in rows]
        except Exception as e:
            self.log_test("Get Existing Tables", "FAIL", f"Error: {str(e)}")
            return []
    
    async def validate_table_existence(self):
        """Validate that all expected tables exist"""
        existing_tables = await self.get_existing_tables()
        
        if not existing_tables:
            self.log_test("Table Existence Validation", "FAIL", "Could not retrieve table list")
            return
        
        all_expected_tables = []
        for service, tables in self.expected_tables.items():
            all_expected_tables.extend(tables)
        
        missing_tables = []
        for table in all_expected_tables:
            if table not in existing_tables:
                missing_tables.append(table)
        
        if missing_tables:
            self.log_test("Table Existence Validation", "FAIL", 
                         f"Missing tables: {', '.join(missing_tables)}")
        else:
            self.log_test("Table Existence Validation", "PASS", 
                         f"All {len(all_expected_tables)} expected tables exist")
        
        # Log existing tables for reference
        self.log_test("Existing Tables Count", "PASS", 
                     f"Found {len(existing_tables)} tables total")
    
    async def validate_table_columns(self):
        """Validate that critical tables have expected columns"""
        try:
            conn = await asyncpg.connect(self.db_url)
            
            for table_name, expected_cols in self.expected_columns.items():
                query = """
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public' AND table_name = $1
                    ORDER BY column_name
                """
                rows = await conn.fetch(query, table_name)
                existing_cols = [row['column_name'] for row in rows]
                
                missing_cols = [col for col in expected_cols if col not in existing_cols]
                
                if missing_cols:
                    self.log_test(f"Table Columns - {table_name}", "FAIL", 
                                f"Missing columns: {', '.join(missing_cols)}")
                else:
                    self.log_test(f"Table Columns - {table_name}", "PASS", 
                                f"All {len(expected_cols)} expected columns exist")
            
            await conn.close()
        except Exception as e:
            self.log_test("Table Columns Validation", "FAIL", f"Error: {str(e)}")
    
    async def validate_foreign_keys(self):
        """Validate critical foreign key relationships"""
        try:
            conn = await asyncpg.connect(self.db_url)
            
            # Check critical foreign keys
            fk_checks = [
                ("order_items", "order_id", "orders", "id"),
                ("order_status_history", "order_id", "orders", "id"),
                ("cylinder_stock", "inventory_id", "inventory_locations", "id"),
                ("stock_movements", "inventory_id", "inventory_locations", "id"),
                ("stock_movements", "stock_id", "cylinder_stock", "id"),
                ("stock_reservations", "inventory_id", "inventory_locations", "id"),
                ("stock_reservations", "stock_id", "cylinder_stock", "id"),
                ("cylinders", "inventory_location_id", "inventory_locations", "id")
            ]
            
            query = """
                SELECT 
                    tc.table_name,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                    AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_schema = 'public'
            """
            
            rows = await conn.fetch(query)
            existing_fks = set()
            for row in rows:
                fk_key = (row['table_name'], row['column_name'], 
                         row['foreign_table_name'], row['foreign_column_name'])
                existing_fks.add(fk_key)
            
            missing_fks = []
            for fk_check in fk_checks:
                if fk_check not in existing_fks:
                    missing_fks.append(f"{fk_check[0]}.{fk_check[1]} -> {fk_check[2]}.{fk_check[3]}")
            
            if missing_fks:
                self.log_test("Foreign Key Validation", "FAIL", 
                             f"Missing foreign keys: {', '.join(missing_fks)}")
            else:
                self.log_test("Foreign Key Validation", "PASS", 
                             f"All {len(fk_checks)} critical foreign keys exist")
            
            await conn.close()
        except Exception as e:
            self.log_test("Foreign Key Validation", "FAIL", f"Error: {str(e)}")
    
    async def validate_indexes(self):
        """Validate that important indexes exist"""
        try:
            conn = await asyncpg.connect(self.db_url)
            
            query = """
                SELECT 
                    schemaname,
                    tablename,
                    indexname,
                    indexdef
                FROM pg_indexes 
                WHERE schemaname = 'public'
                ORDER BY tablename, indexname
            """
            
            rows = await conn.fetch(query)
            indexes_by_table = {}
            for row in rows:
                table = row['tablename']
                if table not in indexes_by_table:
                    indexes_by_table[table] = []
                indexes_by_table[table].append(row['indexname'])
            
            # Check for primary key indexes on critical tables
            critical_tables = list(self.expected_columns.keys())
            missing_pk_indexes = []
            
            for table in critical_tables:
                if table in indexes_by_table:
                    pk_index_found = any('pkey' in idx for idx in indexes_by_table[table])
                    if not pk_index_found:
                        missing_pk_indexes.append(table)
                else:
                    missing_pk_indexes.append(table)
            
            if missing_pk_indexes:
                self.log_test("Primary Key Indexes", "FAIL", 
                             f"Missing primary key indexes: {', '.join(missing_pk_indexes)}")
            else:
                self.log_test("Primary Key Indexes", "PASS", 
                             "All critical tables have primary key indexes")
            
            total_indexes = sum(len(indexes) for indexes in indexes_by_table.values())
            self.log_test("Total Indexes", "PASS", f"Found {total_indexes} indexes across all tables")
            
            await conn.close()
        except Exception as e:
            self.log_test("Index Validation", "FAIL", f"Error: {str(e)}")
    
    async def run_all_validations(self):
        """Run all database schema validations"""
        print("🗄️  Starting Database Schema Validation")
        print("=" * 60)
        
        # Test database connectivity first
        if not await self.connect_to_database():
            print("❌ Cannot connect to database. Stopping validation.")
            return False
        
        await self.validate_table_existence()
        await self.validate_table_columns()
        await self.validate_foreign_keys()
        await self.validate_indexes()
        
        print("\n" + "=" * 60)
        print("📊 Validation Summary")
        print("=" * 60)
        
        passed = len([r for r in self.test_results if r["status"] == "PASS"])
        failed = len([r for r in self.test_results if r["status"] == "FAIL"])
        warnings = len([r for r in self.test_results if r["status"] == "WARN"])
        total = len(self.test_results)
        
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"⚠️  Warnings: {warnings}")
        print(f"📈 Total: {total}")
        
        if failed > 0:
            print("\n🔧 Issues Found:")
            for result in self.test_results:
                if result["status"] == "FAIL":
                    print(f"   • {result['test']}: {result['details']}")
        
        return failed == 0

async def main():
    """Main validation runner"""
    validator = DatabaseSchemaValidator()
    success = await validator.run_all_validations()
    
    if success:
        print("\n🎉 All database schema validations passed!")
        sys.exit(0)
    else:
        print("\n💥 Some database schema validations failed!")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
