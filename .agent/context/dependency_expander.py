# context/dependency_expander.py
#
# Dependency Expander logic. Uses graph database relationships to map active caller/callee edges.

from typing import List, Dict, Any
from repository_intelligence.db.connection import SessionLocal
from repository_intelligence.models.symbol import Symbol, SymbolRelationship
from context.context_package import ResolvedSymbol
from sqlalchemy import or_

class DependencyExpander:
    def expand(self, target_symbols: List[ResolvedSymbol], session=None) -> List[Dict[str, Any]]:
        if not target_symbols:
            return []
        
        close_session = False
        if session is None:
            session = SessionLocal()
            close_session = True
            
        relationships = []
        try:
            # Get matching DB symbol IDs
            names = [s.name for s in target_symbols]
            qnames = [s.qualified_name for s in target_symbols if hasattr(s, "qualified_name") and s.qualified_name]
            all_target_names = list(set(names + qnames))
            
            db_symbols = session.query(Symbol.id).filter(
                or_(
                    Symbol.name.in_(names),
                    Symbol.qualified_name.in_(names)
                )
            ).all()
            symbol_ids = [s[0] for s in db_symbols]
            
            filters = []
            if symbol_ids:
                filters.append(SymbolRelationship.source_symbol_id.in_(symbol_ids))
                filters.append(SymbolRelationship.target_symbol_id.in_(symbol_ids))
            if all_target_names:
                filters.append(SymbolRelationship.target_name.in_(all_target_names))
                
            if filters:
                db_relations = session.query(SymbolRelationship).filter(or_(*filters)).all()
                
                for rel in db_relations:
                    # Resolve names
                    src_sym = session.query(Symbol.name).filter(Symbol.id == rel.source_symbol_id).first()
                    src_name = src_sym[0] if src_sym else str(rel.source_symbol_id)
                    
                    if rel.target_symbol_id:
                        tgt_sym = session.query(Symbol.name).filter(Symbol.id == rel.target_symbol_id).first()
                        tgt_name = tgt_sym[0] if tgt_sym else str(rel.target_symbol_id)
                    else:
                        tgt_name = rel.target_name
                        
                    relationships.append({
                        "source": src_name,
                        "target": tgt_name,
                        "type": rel.relationship_type,
                        "confidence": float(rel.confidence) if rel.confidence else 1.0
                    })
        except Exception as e:
            print(f"[DependencyExpander] Warning: Failed expanding dependencies: {e}")
        finally:
            if close_session:
                session.close()
            
        return relationships
