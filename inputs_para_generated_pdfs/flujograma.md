1     ```mermaid
   2     graph TD
   3         subgraph "Fase 1: Inicio y Clasificación"
   4             A[Start: Operación de Factoring Aprobada] --> B{¿Es una operación nueva?};
   5         end
   6
          subgraph "Ruta A: Cliente Nuevo"
              B --o|Sí| SW_MODULO_CLIENTES["SW: Módulo Clientes"];
              SW_MODULO_CLIENTES --> SW_PASO_1["Paso 1: Crear perfil de cliente (RUC, firmas, contactos, etc)"];
              SW_PASO_1 --> SW_PASO_2["Paso 2: Crear Repositorio Google Drive (Razón Social) con subcarpetas Legal y Riesgos"];
              SW_PASO_2 --> SW_GEN_DOCS["SW: Con datos del cliente y plantillas, se generan Contrato, Pagaré y Acuerdos"];
              SW_GEN_DOCS --> SW_SEND_KEYNUA["SW: Se envía a Keynua vía API para firma electrónica"];
              SW_SEND_KEYNUA --> G{5. ¿Firma de documentos completa?};
              G --o|No| H_STANDBY[Operación en Stand-By];
              G --o|Sí| I[6. Registrar operación en flujos Micro/Macro];
          end

          subgraph "Ruta B: Cliente Existente (Anexo)"
              B --o|No| J[1. Generar carpeta para el nuevo anexo];
              J --> K[2. Subir facturas a carpeta compartida];
              K --> L[3. Enviar correo de confirmación al pagador];
              L --> M{4. ¿Pagador contestó?};
              M --o|No| N_STANDBY[Operación en Stand-By];
              M --o|Sí| O[5. Preparar Proforma (PDF) y Solicitud (Word)];
          end

          subgraph "Fase 2: Verificación y Registro"
              I --> P[7. Subir XML de facturas a Cavali];
              O --> P;
              P --> Q{8. ¿Hay conformidad de las facturas?};
              Q --o|No| R_STANDBY[Operación en Stand-By];
          end

          subgraph "Fase 3: Cierre"