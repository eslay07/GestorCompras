

# Nuevas acciones agregadas:
                department_input = driver.find_element(By.ID, 'txtDepartment')
                department_input.clear()
                department_input.send_keys('Bodega')
                time.sleep(1)
                department_input.send_keys(Keys.DOWN, Keys.RETURN)

                employee_input = driver.find_element(By.ID, 'cmbEmpleadoReasigna')
                employee_input.click()
                employee_input.send_keys('Bryan Javier')
                time.sleep(1)
                employee_input.send_keys(Keys.DOWN, Keys.RETURN)

                textarea_observation = driver.find_element(By.ID, 'txtaObsTareaFinalReasigna')
                textarea_observation.send_keys('TRABAJO REALIZADO')
                time.sleep(1)

                btn_aceptar = driver.find_element(By.ID, 'btnGrabarEjecucionTarea')
                btn_aceptar.click()
                time.sleep(2)

                btn_aceptar = driver.find_element(By.ID, 'btnSmsCustomOk')
                btn_aceptar.click()
                time.sleep(2)